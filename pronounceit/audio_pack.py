from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .audio import audio_file_has_content
from .dictionary import normalize_term


PACK_SCHEMA_VERSION = 2
AUDIO_ASSET_NAMESPACE = "pronounceit-audio-v2"
DEFAULT_MANIFEST_URL = (
    "https://github.com/caleblee789/PronounceIt/releases/download/"
    "audio-pack-v2/pack-manifest.json"
)
DEFAULT_CACHE_BYTES = 250 * 1024 * 1024
DOWNLOAD_SPACE_MARGIN_BYTES = 100 * 1024 * 1024


class AudioPackError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioPackStatus:
    installed: bool
    compatible: bool
    version: str = ""
    downloaded_shards: int = 0
    total_shards: int = 0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    message: str = "Offline pronunciation pack is not installed."


def audio_asset_id(term: str) -> str:
    normalized = normalize_term(term)
    value = f"{AUDIO_ASSET_NAMESPACE}\0{normalized}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def dictionary_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_supported_pack_version(version: str) -> bool:
    return version == "2" or version.startswith("2.") or version.startswith("2-")


def validate_manifest(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise AudioPackError("audio pack manifest must be a JSON object")
    if raw.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise AudioPackError("unsupported audio pack manifest version")
    version = str(raw.get("packVersion") or "").strip()
    dictionary_hash = str(raw.get("dictionarySha256") or "").strip().casefold()
    review_hash = str(raw.get("reviewLedgerSha256") or "").strip().casefold()
    strategies = raw.get("synthesisStrategyCounts")
    shards = raw.get("shards")
    if (
        not version
        or not is_supported_pack_version(version)
        or len(dictionary_hash) != 64
        or len(review_hash) != 64
        or not isinstance(strategies, dict)
        or not isinstance(shards, list)
    ):
        raise AudioPackError("audio pack manifest is missing required fields")
    if (
        any(key not in {"azure-native", "manual-sapi"} for key in strategies)
        or any(not isinstance(value, int) or value < 0 for value in strategies.values())
    ):
        raise AudioPackError("audio pack manifest uses a forbidden synthesis strategy")
    seen: set[str] = set()
    for shard in shards:
        if not isinstance(shard, dict):
            raise AudioPackError("audio pack shard entry is invalid")
        shard_id = str(shard.get("id") or "").casefold()
        filename = str(shard.get("file") or "")
        checksum = str(shard.get("sha256") or "").casefold()
        size = shard.get("size")
        if (
            len(shard_id) != 1
            or shard_id not in "0123456789abcdef"
            or shard_id in seen
            or Path(filename).name != filename
            or not filename.endswith(".zip")
            or len(checksum) != 64
            or not isinstance(size, int)
            or size <= 0
        ):
            raise AudioPackError(f"invalid audio pack shard: {shard_id or '(missing id)'}")
        seen.add(shard_id)
    if seen != set("0123456789abcdef"):
        raise AudioPackError("audio pack manifest must contain all 16 shards")
    return raw


class AudioPackManager:
    def __init__(
        self,
        addon_root: Path,
        manifest_url: str | None = None,
        cache_bytes: int = DEFAULT_CACHE_BYTES,
    ) -> None:
        self.addon_root = addon_root
        self.dictionary_path = addon_root / "data" / "medical_pronunciations.json"
        self.pack_root = addon_root / "user_files" / "audio_packs"
        self.cache_root = addon_root / "user_files" / "audio_cache"
        self.manifest_url = (
            manifest_url
            or os.environ.get("PRONOUNCEIT_AUDIO_PACK_MANIFEST_URL", "").strip()
            or DEFAULT_MANIFEST_URL
        )
        self.cache_bytes = max(0, int(cache_bytes))
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_event = threading.Event()
        self._dictionary_hash: str | None = None

    @property
    def state_path(self) -> Path:
        return self.pack_root / "installed.json"

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._pause_event.set()

    def status(self, verify_hashes: bool = False) -> AudioPackStatus:
        manifest = self._load_local_manifest()
        if manifest is None:
            return AudioPackStatus(False, False)
        compatible = self._dictionary_is_compatible(manifest)
        complete = 0
        downloaded_bytes = 0
        for shard in manifest["shards"]:
            path = self._shard_path(manifest, shard)
            if not path.is_file():
                continue
            try:
                size_matches = path.stat().st_size == int(shard["size"])
            except OSError:
                size_matches = False
            hash_matches = not verify_hashes or (
                size_matches and file_sha256(path) == str(shard["sha256"]).casefold()
            )
            if size_matches and hash_matches:
                complete += 1
                downloaded_bytes += path.stat().st_size
        total = len(manifest["shards"])
        total_bytes = sum(int(shard["size"]) for shard in manifest["shards"])
        installed = complete == total and compatible
        if not compatible:
            message = "Installed offline pronunciation pack does not match this dictionary version."
        elif installed:
            message = f"Offline pronunciation pack {manifest['packVersion']} is installed and ready."
        else:
            message = f"Offline pronunciation pack download is incomplete ({complete}/{total} files)."
        return AudioPackStatus(
            installed=installed,
            compatible=compatible,
            version=str(manifest["packVersion"]),
            downloaded_shards=complete,
            total_shards=total,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            message=message,
        )

    def download(
        self,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> AudioPackStatus:
        self._cancel_event.clear()
        manifest = self._fetch_manifest()
        if not self._dictionary_is_compatible(manifest):
            raise AudioPackError("audio pack was built for a different dictionary version")
        previous_version = self._local_state_version()
        version_dir = self.pack_root / str(manifest["packVersion"])
        version_dir.mkdir(parents=True, exist_ok=True)
        self._write_json_atomic(version_dir / "pack-manifest.json", manifest)

        remaining_bytes = sum(
            int(shard["size"])
            for shard in manifest["shards"]
            if not self._valid_shard(self._shard_path(manifest, shard), shard)
        )
        try:
            free_bytes = shutil.disk_usage(self.pack_root.parent).free
        except OSError as exc:
            raise AudioPackError(f"could not check free disk space: {exc}") from exc
        required_bytes = remaining_bytes + DOWNLOAD_SPACE_MARGIN_BYTES
        if free_bytes < required_bytes:
            raise AudioPackError(
                "not enough free disk space for the audio pack "
                f"(need {required_bytes / (1024 * 1024):.0f} MiB, "
                f"have {free_bytes / (1024 * 1024):.0f} MiB)"
            )

        total_bytes = sum(int(shard["size"]) for shard in manifest["shards"])
        complete_bytes = 0
        for shard in manifest["shards"]:
            self._wait_if_paused()
            self._raise_if_cancelled()
            target = self._shard_path(manifest, shard)
            if self._valid_shard(target, shard):
                complete_bytes += int(shard["size"])
                if progress:
                    progress(complete_bytes, total_bytes, str(shard["id"]))
                continue
            self._download_shard(manifest, shard, target, complete_bytes, total_bytes, progress)
            complete_bytes += int(shard["size"])
        self.pack_root.mkdir(parents=True, exist_ok=True)
        self._write_json_atomic(self.state_path, {"packVersion": manifest["packVersion"]})
        if previous_version and previous_version != str(manifest["packVersion"]):
            shutil.rmtree(self.pack_root / previous_version, ignore_errors=True)
            shutil.rmtree(self.cache_root / previous_version, ignore_errors=True)
        return self.status(verify_hashes=True)

    def verify(self) -> AudioPackStatus:
        return self.status(verify_hashes=True)

    def remove(self) -> None:
        version = self._local_state_version()
        if version:
            shutil.rmtree(self.pack_root / version, ignore_errors=True)
            shutil.rmtree(self.cache_root / version, ignore_errors=True)
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError as exc:
            raise AudioPackError(str(exc)) from exc

    def resolve(self, term: str) -> Path | None:
        manifest = self._load_local_manifest()
        if manifest is None or not self._dictionary_is_compatible(manifest):
            return None
        asset_id = audio_asset_id(term)
        shard_id = asset_id[0]
        shard = next((item for item in manifest["shards"] if item["id"] == shard_id), None)
        if shard is None:
            return None
        shard_path = self._shard_path(manifest, shard)
        if not self._valid_shard(shard_path, shard, checksum=False):
            return None
        cache_path = self.cache_root / str(manifest["packVersion"]) / f"{asset_id}.mp3"
        if audio_file_has_content(cache_path):
            try:
                os.utime(cache_path, None)
            except OSError:
                pass
            return cache_path
        member = f"audio/{asset_id}.mp3"
        try:
            with zipfile.ZipFile(shard_path) as archive:
                data = archive.read(member)
            if not data:
                return None
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_suffix(".mp3.tmp")
            temp_path.write_bytes(data)
            os.replace(temp_path, cache_path)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None
        self._enforce_cache_limit(keep=cache_path)
        return cache_path if audio_file_has_content(cache_path) else None

    def _fetch_manifest(self) -> dict[str, Any]:
        try:
            request = urllib.request.Request(
                self.manifest_url,
                headers={"User-Agent": "PronounceIt-audio-pack/1"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.URLError) as exc:
            raise AudioPackError(f"could not download audio pack manifest: {exc}") from exc
        return validate_manifest(raw)

    def _load_local_manifest(self) -> dict[str, Any] | None:
        """Load an installed manifest, or a persisted partial-download manifest.

        ``installed.json`` is deliberately written only after every shard has
        passed validation.  The manifest is written before downloading shards,
        though, and must remain discoverable after an Anki restart so the UI
        can show progress and the downloader can resume from ``.part`` files.
        """
        version = self._local_state_version()
        candidates: list[Path] = []
        if version:
            candidates.append(self.pack_root / version / "pack-manifest.json")
        else:
            try:
                candidates.extend(
                    sorted(
                        self.pack_root.glob("*/pack-manifest.json"),
                        key=lambda path: path.parent.name,
                        reverse=True,
                    )
                )
            except OSError:
                return None

        for path in candidates:
            try:
                manifest = validate_manifest(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, AudioPackError):
                continue
            if str(manifest["packVersion"]) == path.parent.name:
                return manifest
        return None

    def _local_state_version(self) -> str:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return str(state.get("packVersion") or "").strip()
        except (OSError, AttributeError, json.JSONDecodeError):
            return ""

    def _dictionary_is_compatible(self, manifest: dict[str, Any]) -> bool:
        try:
            if self._dictionary_hash is None:
                self._dictionary_hash = dictionary_sha256(self.dictionary_path)
            return self._dictionary_hash == manifest["dictionarySha256"]
        except OSError:
            return False

    def _shard_path(self, manifest: dict[str, Any], shard: dict[str, Any]) -> Path:
        return self.pack_root / str(manifest["packVersion"]) / str(shard["file"])

    def _valid_shard(
        self,
        path: Path,
        shard: dict[str, Any],
        checksum: bool = True,
    ) -> bool:
        try:
            if not path.is_file() or path.stat().st_size != int(shard["size"]):
                return False
            return not checksum or file_sha256(path) == str(shard["sha256"]).casefold()
        except OSError:
            return False

    def _download_shard(
        self,
        manifest: dict[str, Any],
        shard: dict[str, Any],
        target: Path,
        base_bytes: int,
        total_bytes: int,
        progress: Callable[[int, int, str], None] | None,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        existing = partial.stat().st_size if partial.exists() else 0
        url = str(shard.get("url") or "")
        if not url:
            url = urllib.parse.urljoin(self.manifest_url, str(shard["file"]))
        request = urllib.request.Request(url)
        request.add_header("User-Agent", "PronounceIt-audio-pack/1")
        if existing:
            request.add_header("Range", f"bytes={existing}-")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                append = existing > 0 and getattr(response, "status", 200) == 206
                if not append:
                    existing = 0
                mode = "ab" if append else "wb"
                with partial.open(mode) as handle:
                    while True:
                        self._wait_if_paused()
                        self._raise_if_cancelled()
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        existing += len(chunk)
                        if progress:
                            progress(base_bytes + existing, total_bytes, str(shard["id"]))
                    handle.flush()
                    os.fsync(handle.fileno())
        except (OSError, urllib.error.URLError) as exc:
            raise AudioPackError(f"could not download shard {shard['id']}: {exc}") from exc
        if not self._valid_shard(partial, shard):
            raise AudioPackError(f"downloaded shard {shard['id']} failed checksum validation")
        os.replace(partial, target)

    def _wait_if_paused(self) -> None:
        while not self._pause_event.wait(timeout=0.25):
            self._raise_if_cancelled()

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise AudioPackError("audio pack download cancelled")

    def _write_json_atomic(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def _enforce_cache_limit(self, keep: Path) -> None:
        if self.cache_bytes <= 0:
            return
        files = []
        total = 0
        try:
            for path in self.cache_root.glob("*/*.mp3"):
                stat = path.stat()
                total += stat.st_size
                files.append((stat.st_mtime, stat.st_size, path))
        except OSError:
            return
        for _mtime, size, path in sorted(files):
            if total <= self.cache_bytes:
                break
            if path == keep:
                continue
            try:
                path.unlink()
                total -= size
            except OSError:
                continue
