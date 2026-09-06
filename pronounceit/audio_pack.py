from __future__ import annotations

import hashlib
import json
import os
import re
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


PACK_SCHEMA_VERSION = 3
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
    return bool(re.fullmatch(r"[23](?:[.-][A-Za-z0-9._-]+)?", version))


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _validate_v3(raw: dict[str, Any]) -> None:
    generation, phonemes, review, assets = (raw.get(k) for k in ("generation", "phonemeInput", "review", "assets"))
    if not all(isinstance(value, dict) for value in (generation, phonemes, review, assets)):
        raise AudioPackError("audio pack is missing generation and pronunciation metadata")
    if (generation.get("provider") != "kokoro-local"
        or not all(generation.get(k) for k in ("model", "modelRevision", "voice", "speed"))
        or not _sha256(generation.get("bindingSha256"))
        or phonemes.get("alphabet") != "kokoro-us-v1"
        or not _sha256(phonemes.get("recordsSha256"))
        or review.get("methodApproval") != "accepted-kokoro-pilot"
        or review.get("pilotClipCount") != 10
        or not _sha256(review.get("pilotBindingSha256"))):
        raise AudioPackError("audio pack has invalid provider or pilot approval metadata")
    if raw.get("assetCount") != len(assets) or phonemes.get("termCount") != len(assets):
        raise AudioPackError("audio pack pronunciation coverage differs")
    for identifier, asset in assets.items():
        if (not _sha256(identifier) or not isinstance(asset, dict)
            or not _sha256(asset.get("sha256")) or not _sha256(asset.get("phonemeInputSha256"))
            or asset.get("clipReviewStatus") not in {"accepted", "unreviewed"}
            or asset.get("reviewStatus") not in {"listening-approved", "reference-backed", "unverified-estimate"}):
            raise AudioPackError("audio pack contains invalid asset provenance")


def validate_manifest(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise AudioPackError("audio pack manifest must be a JSON object")
    schema = raw.get("schemaVersion")
    if type(schema) is not int or schema not in {2, 3}:
        raise AudioPackError("unsupported audio pack manifest version")
    version = str(raw.get("packVersion") or "").strip()
    dictionary_hash = str(raw.get("dictionarySha256") or "").strip().casefold()
    review_hash = str(raw.get("reviewLedgerSha256") or "").strip().casefold()
    strategies = raw.get("synthesisStrategyCounts")
    shards = raw.get("shards")
    if (
        not version
        or not is_supported_pack_version(version)
        or not _sha256(dictionary_hash)
        or not version.startswith(str(schema))
        or (schema == 2 and (not _sha256(review_hash) or not isinstance(strategies, dict)))
        or not isinstance(shards, list)
    ):
        raise AudioPackError("audio pack manifest is missing required fields")
    if schema == 2 and (
        any(key not in {"azure-native", "manual-sapi"} for key in strategies)
        or any(not isinstance(value, int) or value < 0 for value in strategies.values())
    ):
        raise AudioPackError("audio pack manifest uses a forbidden synthesis strategy")
    if schema == 3:
        _validate_v3(raw)
    seen: set[str] = set()
    seen_files: set[str] = set()
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
            or filename in seen_files
            or "/" in filename or "\\" in filename
            or Path(filename).name != filename
            or not filename.endswith(".zip")
            or not _sha256(checksum)
            or not isinstance(size, int)
            or size <= 0
        ):
            raise AudioPackError(f"invalid audio pack shard: {shard_id or '(missing id)'}")
        seen.add(shard_id)
        seen_files.add(filename)
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
            or self._candidate_manifest_url()
            or DEFAULT_MANIFEST_URL
        )
        self.cache_bytes = max(0, int(cache_bytes))
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_event = threading.Event()
        self._dictionary_hash: str | None = None
        self._dictionary_stamp: tuple[int, int, int] | None = None
        self._manifest_cache: tuple[Path, int, int, dict[str, Any]] | None = None

    def _candidate_manifest_url(self) -> str:
        try:
            release = json.loads((self.addon_root / "data/audio-pack-release.json").read_text(encoding="utf-8"))
            url = str(release.get("manifestUrl") or "")
            if release.get("schemaVersion") == 3 and urllib.parse.urlparse(url).scheme == "https":
                return url
        except (OSError, ValueError, AttributeError):
            pass
        return ""

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
            if self._valid_shard(path, shard, checksum=verify_hashes):
                complete += 1
                downloaded_bytes += int(shard["size"])
            else:
                partial = path.with_suffix(path.suffix + ".part")
                try:
                    downloaded_bytes += min(partial.stat().st_size, int(shard["size"]))
                except OSError:
                    pass
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

        remaining_bytes = 0
        for shard in manifest["shards"]:
            target = self._shard_path(manifest, shard)
            if not self._valid_shard(target, shard):
                target.unlink(missing_ok=True)
                existing = self._prepare_partial(target, shard)
                if not self._valid_shard(target, shard, checksum=False):
                    remaining_bytes += int(shard["size"]) - existing
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
        try:
            # Incomplete downloads have no installed.json, and an update may
            # have left more than one version on disk.
            for root in (self.pack_root, self.cache_root):
                if root.exists():
                    for directory in root.iterdir():
                        if is_supported_pack_version(directory.name) and directory.is_dir():
                            if directory.is_symlink():
                                directory.unlink()
                            else:
                                shutil.rmtree(directory)
            self.state_path.unlink(missing_ok=True)
        except OSError as exc:
            raise AudioPackError(str(exc)) from exc
        self._manifest_cache = None

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
        asset = manifest.get("assets", {}).get(asset_id)
        if manifest["schemaVersion"] == 3 and asset is None:
            return None
        if asset:
            cache_path = cache_path.with_name(f"{asset_id}-{asset['sha256'][:16]}.mp3")
        if audio_file_has_content(cache_path) and (not asset or file_sha256(cache_path) == asset["sha256"]):
            try:
                os.utime(cache_path, None)
            except OSError:
                pass
            return cache_path
        member = f"audio/{asset_id}.mp3"
        try:
            with zipfile.ZipFile(shard_path) as archive:
                data = archive.read(member)
            if not data or (asset and hashlib.sha256(data).hexdigest() != asset["sha256"]):
                return None
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_suffix(".mp3.tmp")
            temp_path.write_bytes(data)
            os.replace(temp_path, cache_path)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None
        self._enforce_cache_limit(keep=cache_path)
        return cache_path if audio_file_has_content(cache_path) else None

    def playback_metadata(self, term: str) -> dict[str, str]:
        manifest = self._load_local_manifest()
        if manifest and self._dictionary_is_compatible(manifest) and manifest["schemaVersion"] == 3:
            asset = manifest["assets"].get(audio_asset_id(term), {})
            return {"source": "recorded", "provider": manifest["generation"]["provider"],
                    "reviewStatus": asset.get("clipReviewStatus", "unreviewed"),
                    "packVersion": manifest["packVersion"]}
        return {"source": "azure", "provider": "azure-speech", "reviewStatus": "passed"}

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
                stamp = path.stat()
                cache = self._manifest_cache
                if cache and cache[:3] == (path, stamp.st_mtime_ns, stamp.st_size):
                    return cache[3]
                manifest = validate_manifest(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, AudioPackError):
                continue
            if str(manifest["packVersion"]) == path.parent.name:
                self._manifest_cache = (path, stamp.st_mtime_ns, stamp.st_size, manifest)
                return manifest
        return None

    def _local_state_version(self) -> str:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            version = str(state.get("packVersion") or "").strip()
            return version if is_supported_pack_version(version) else ""
        except (OSError, UnicodeError, AttributeError, json.JSONDecodeError):
            return ""

    def _dictionary_is_compatible(self, manifest: dict[str, Any]) -> bool:
        try:
            stat = self.dictionary_path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            if self._dictionary_hash is None or stamp != self._dictionary_stamp:
                self._dictionary_hash = dictionary_sha256(self.dictionary_path)
                self._dictionary_stamp = stamp
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
        existing = self._prepare_partial(target, shard)
        if self._valid_shard(target, shard):
            return
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
                if append:
                    content_range = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if (not content_range or int(content_range[1]) != existing
                            or int(content_range[3]) != int(shard["size"])
                            or not existing <= int(content_range[2]) < int(shard["size"])):
                        partial.unlink(missing_ok=True)
                        raise AudioPackError(f"shard {shard['id']} returned an invalid resume range; retry the download")
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
                        if existing > int(shard["size"]):
                            raise AudioPackError(f"downloaded shard {shard['id']} exceeds its expected size")
                        if progress:
                            progress(base_bytes + existing, total_bytes, str(shard["id"]))
                    handle.flush()
                    os.fsync(handle.fileno())
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                partial.unlink(missing_ok=True)
            raise AudioPackError(f"could not download shard {shard['id']}: {exc}") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise AudioPackError(f"could not download shard {shard['id']}: {exc}") from exc
        if partial.stat().st_size < int(shard["size"]):
            raise AudioPackError(f"downloaded shard {shard['id']} is incomplete; resume to finish")
        if not self._valid_shard(partial, shard):
            partial.unlink(missing_ok=True)
            raise AudioPackError(f"downloaded shard {shard['id']} failed checksum validation")
        os.replace(partial, target)

    def _prepare_partial(self, target: Path, shard: dict[str, Any]) -> int:
        partial = target.with_suffix(target.suffix + ".part")
        try:
            size = partial.stat().st_size if partial.exists() else 0
            if size >= int(shard["size"]):
                if self._valid_shard(partial, shard):
                    os.replace(partial, target)
                else:
                    partial.unlink()
                return 0
            return size
        except OSError as exc:
            raise AudioPackError(f"could not prepare shard {shard['id']}: {exc}") from exc

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
