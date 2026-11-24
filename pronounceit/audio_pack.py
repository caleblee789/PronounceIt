from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .audio import audio_file_has_content
from .dictionary import BUNDLED_PRONUNCIATION_EXCLUSIONS, normalize_term


PACK_SCHEMA_VERSION = 3
AUDIO_ASSET_NAMESPACE = "pronounceit-audio-v2"
MARIN_REALTIME_MODEL = "gpt-realtime-2.1-mini"
MARIN_PILOT_CLIP_COUNT = 10
DEFAULT_MANIFEST_URL = (
    "https://github.com/caleblee789/PronounceIt/releases/download/"
    "audio-pack-v2/pack-manifest.json"
)
DEFAULT_CACHE_BYTES = 250 * 1024 * 1024
DOWNLOAD_SPACE_MARGIN_BYTES = 100 * 1024 * 1024


class AudioPackError(RuntimeError):
    pass


class AudioPackCancelled(AudioPackError):
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
    active_version: str = ""
    verified: bool = False


def manifest_content_sha256(manifest: dict[str, Any]) -> str:
    """Bind a release independently of installed JSON whitespace."""
    return hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


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
    generation, review, assets = (raw.get(k) for k in ("generation", "review", "assets"))
    if not all(isinstance(value, dict) for value in (generation, review, assets)):
        raise AudioPackError("audio pack is missing generation and pronunciation metadata")
    provider = generation.get("provider")
    marin = provider == "openai" and generation.get("model") == MARIN_REALTIME_MODEL
    if provider == "kokoro-local":
        inputs = raw.get("phonemeInput")
        input_hash = "phonemeInputSha256"
        provider_valid = (all(generation.get(k) for k in ("model", "modelRevision", "voice", "speed"))
                          and isinstance(inputs, dict) and inputs.get("alphabet") == "kokoro-us-v1"
                          and review.get("methodApproval") == "accepted-kokoro-pilot"
                          and review.get("pilotClipCount") == 10)
    elif provider == "openai":
        inputs = raw.get("speechInput")
        input_hash = "inputSha256"
        automated = review.get("methodApproval") == "automated-openai-pilot"
        if marin:
            listened = review.get("listenedAssetIds")
            profile_valid = (
                generation.get("voice") == "marin" and generation.get("sampleRate") == 24000
                and raw.get("format") == "audio-24khz-48kbitrate-mono-mp3"
                and review.get("methodApproval") == "accepted-openai-realtime-pilot"
                and review.get("pilotClipCount") == MARIN_PILOT_CLIP_COUNT
                and isinstance(listened, list) and len(listened) == MARIN_PILOT_CLIP_COUNT
                and all(_sha256(identifier) for identifier in listened)
                and len(set(listened)) == MARIN_PILOT_CLIP_COUNT
            )
        else:
            approval_valid = (review.get("methodApproval") == "accepted-openai-pilot"
                              or (automated and generation.get("model") == "tts-1-hd"
                                  and review.get("pilotAudioIntegrityChecked") is True))
            profile_valid = (
                generation.get("model") in {"tts-1", "tts-1-hd"} and generation.get("voice") == "nova"
                and approval_valid and review.get("pilotClipCount") == 60
            )
        provider_valid = (
            profile_valid and generation.get("speed") == 1 and "phonemeInput" not in raw
            and isinstance(inputs, dict) and review.get("libraryListeningAccuracyMeasured") is False
        )
    else:
        raise AudioPackError("audio pack has unsupported provider metadata")
    if (not provider_valid or not _sha256(generation.get("bindingSha256"))
        or not _sha256(inputs.get("recordsSha256"))
        or not _sha256(review.get("pilotBindingSha256"))):
        raise AudioPackError("audio pack has invalid provider or pilot approval metadata")
    if raw.get("assetCount") != len(assets) or inputs.get("termCount") != len(assets):
        raise AudioPackError("audio pack pronunciation coverage differs")
    if marin:
        approved = {identifier for identifier, asset in assets.items() if isinstance(asset, dict)
                    and (asset.get("clipReviewStatus") == "accepted" or asset.get("reviewStatus") == "listening-approved")}
        if approved != set(listened) or any(
            assets[identifier].get("clipReviewStatus") != "accepted"
            or assets[identifier].get("reviewStatus") != "listening-approved" for identifier in approved
        ):
            raise AudioPackError("Marin pack assets differ from its listened pilot")
    for identifier, asset in assets.items():
        if (not _sha256(identifier) or not isinstance(asset, dict)
            or not _sha256(asset.get("sha256")) or not _sha256(asset.get(input_hash))
            or asset.get("clipReviewStatus") not in {"accepted", "unreviewed"}
            or asset.get("reviewStatus") not in {"listening-approved", "reference-backed", "unverified-estimate"}):
            raise AudioPackError("audio pack contains invalid asset provenance")
        if provider == "openai" and automated and (asset.get("clipReviewStatus") != "unreviewed"
                                                   or asset.get("reviewStatus") == "listening-approved"):
            raise AudioPackError("automated audio checks cannot claim listening approval")


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


def read_release_metadata(addon_root: Path) -> dict[str, Any]:
    try:
        release = json.loads((addon_root / "data/audio-pack-release.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return release if isinstance(release, dict) and release.get("schemaVersion") == 3 else {}


class AudioPackManager:
    def __init__(
        self,
        addon_root: Path,
        manifest_url: str | None = None,
        cache_bytes: int = DEFAULT_CACHE_BYTES,
    ) -> None:
        self.addon_root = addon_root
        self.dictionary_path = addon_root / "data" / "audio_pronunciations.json"
        # Older add-ons and standalone pack tooling used the original dictionary.
        if not self.dictionary_path.exists():
            self.dictionary_path = addon_root / "data" / "medical_pronunciations.json"
        self.pack_root = addon_root / "user_files" / "audio_packs"
        self.cache_root = addon_root / "user_files" / "audio_cache"
        self._manifest_url_override = (
            manifest_url
            or os.environ.get("PRONOUNCEIT_AUDIO_PACK_MANIFEST_URL", "").strip()
        )
        self._source_url = ""
        self.cache_bytes = max(0, int(cache_bytes))
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_event = threading.Event()
        self._promotion_lock = threading.Lock()
        self._download_promoted = False
        self._dictionary_cache: tuple[tuple[int, int, int], str] | None = None
        self._compatibility_cache: tuple[dict[str, Any], str] | None = None
        self._manifest_cache: tuple[Path, int, int, dict[str, Any]] | None = None

    @property
    def manifest_url(self) -> str:
        return self._manifest_url_override or self._source_url or self._candidate_manifest_url() or DEFAULT_MANIFEST_URL

    @staticmethod
    def _configured_version(release: dict[str, Any]) -> str:
        version = str(release.get("releaseTag") or "").removeprefix("audio-pack-v")
        return version if is_supported_pack_version(version) else ""

    def _candidate_manifest_url(self) -> str:
        release = read_release_metadata(self.addon_root)
        if not release:
            return ""
        # A separately supplied pack must match the same release binding.
        local_manifest = self.addon_root / "data/pack-manifest.json"
        try:
            manifest = validate_manifest(json.loads(local_manifest.read_text(encoding="utf-8")))
            if (
                manifest["dictionarySha256"] == release.get("dictionarySha256")
                and manifest_content_sha256(manifest) == release.get("packManifestContentSha256")
                and all(
                    (local_manifest.parent / shard["file"]).is_file()
                    and (local_manifest.parent / shard["file"]).stat().st_size == shard["size"]
                    for shard in manifest["shards"]
                )
            ):
                return local_manifest.resolve().as_uri()
        except (OSError, ValueError, TypeError, AudioPackError):
            pass
        url = str(release.get("manifestUrl") or "")
        return url if url.startswith("https://") else ""

    @property
    def state_path(self) -> Path:
        return self.pack_root / "installed.json"

    def pause(self) -> bool:
        with self._promotion_lock:
            if self._download_promoted or self._cancel_event.is_set():
                return False
            self._pause_event.clear()
            return True

    def resume(self) -> None:
        self._pause_event.set()

    def prepare_download(self) -> None:
        with self._promotion_lock:
            self._cancel_event.clear()
            self._pause_event.set()
            self._download_promoted = False

    def cancel(self) -> bool:
        with self._promotion_lock:
            if self._download_promoted:
                return False
            self._cancel_event.set()
            self._pause_event.set()
            return True

    def status(self, verify_hashes: bool = False) -> AudioPackStatus:
        active_version = self._local_state_version()
        version = self._configured_version(read_release_metadata(self.addon_root))
        manifest = self._manifest_for_version(version) if version else self._legacy_target_manifest(active_version)
        if manifest is None:
            message = (
                "An audio library update is available."
                if active_version and version and active_version != version
                else "Offline pronunciation pack is not installed."
            )
            return AudioPackStatus(False, False, version=version, message=message, active_version=active_version)
        return self._manifest_status(manifest, active_version, verify_hashes)

    def _manifest_status(
        self,
        manifest: dict[str, Any],
        active_version: str,
        verify_hashes: bool,
        check_cancelled: Callable[[], None] | None = None,
    ) -> AudioPackStatus:
        version = str(manifest["packVersion"]).strip()
        compatible = self._dictionary_is_compatible(manifest)
        complete = 0
        downloaded_bytes = 0
        for shard in manifest["shards"]:
            if check_cancelled:
                check_cancelled()
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
        installed = complete == total and compatible and active_version == version
        if not compatible:
            message = "Offline pronunciation pack does not match this dictionary version."
        elif installed:
            message = f"Offline pronunciation pack {version} is installed and ready."
        elif complete == total:
            message = "Offline pronunciation pack is ready to finish installing."
        else:
            message = f"Offline pronunciation pack download is incomplete ({complete}/{total} files)."
        return AudioPackStatus(
            installed=installed,
            compatible=compatible,
            version=version,
            downloaded_shards=complete,
            total_shards=total,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            message=message,
            active_version=active_version,
            verified=installed and verify_hashes,
        )

    def download(
        self,
        progress: Callable[[int, int, str], None] | None = None,
        *,
        prepared: bool = False,
    ) -> AudioPackStatus:
        if not prepared:
            self.prepare_download()
        self._raise_if_cancelled()
        if not self._manifest_url_override:
            self._source_url = self._candidate_manifest_url() or DEFAULT_MANIFEST_URL
        manifest = self._fetch_manifest()
        self._raise_if_cancelled()
        if not self._dictionary_is_compatible(manifest):
            raise AudioPackError("audio pack was built for a different dictionary version")
        previous_version = self._local_state_version()
        version = str(manifest["packVersion"]).strip()
        previous_manifest = self._manifest_for_version(version)
        if (previous_version == version and previous_manifest and previous_manifest != manifest
                and self._dictionary_is_compatible(previous_manifest)):
            raise AudioPackError("audio pack manifest changed without a new pack version")
        manifest_path = self.pack_root / version / "pack-manifest.json"
        if previous_manifest != manifest:
            self._write_json_atomic(manifest_path, manifest)
        stamp = manifest_path.stat()
        self._manifest_cache = (manifest_path, stamp.st_mtime_ns, stamp.st_size, manifest)

        remaining_bytes = 0
        ready_shards = set()
        for shard in manifest["shards"]:
            self._raise_if_cancelled()
            target = self._shard_path(manifest, shard)
            if self._valid_shard(target, shard):
                ready_shards.add(shard["id"])
                continue
            target.unlink(missing_ok=True)
            existing = self._prepare_partial(target, shard)
            if self._valid_shard(target, shard, checksum=False):
                ready_shards.add(shard["id"])
            else:
                remaining_bytes += int(shard["size"]) - existing
        if remaining_bytes:
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
            if shard["id"] in ready_shards:
                complete_bytes += int(shard["size"])
                if progress:
                    progress(complete_bytes, total_bytes, str(shard["id"]))
                continue
            self._download_shard(shard, target, complete_bytes, total_bytes, progress)
            complete_bytes += int(shard["size"])

        verified = self._manifest_status(manifest, version, True, self._raise_if_cancelled)
        if not verified.installed:
            raise AudioPackError(f"could not verify the new offline pronunciation pack: {verified.message}")
        # Cancellation and activation meet at the installed pointer. Once it
        # changes, the new pack is active and can no longer pause or cancel.
        while True:
            self._wait_if_paused()
            with self._promotion_lock:
                self._raise_if_cancelled()
                if self._pause_event.is_set():
                    self._write_json_atomic(self.state_path, {"packVersion": version})
                    self._download_promoted = True
                    break
        if previous_version and previous_version != version:
            shutil.rmtree(self.pack_root / previous_version, ignore_errors=True)
            shutil.rmtree(self.cache_root / previous_version, ignore_errors=True)
        return verified

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
        if normalize_term(term) in BUNDLED_PRONUNCIATION_EXCLUSIONS:
            return None
        manifest = self._active_manifest()
        if manifest is None:
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
        manifest = self._active_manifest()
        if manifest and manifest["schemaVersion"] == 3:
            return {"provider": manifest["generation"]["provider"],
                    "packVersion": manifest["packVersion"]}
        return {"provider": "azure-speech"}

    def _fetch_manifest(self) -> dict[str, Any]:
        try:
            request = urllib.request.Request(
                self.manifest_url,
                headers={"User-Agent": "PronounceIt-audio-pack/1"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            release = read_release_metadata(self.addon_root)
            expected_hash = release.get("packManifestSha256")
            if (not self._manifest_url_override and request.full_url == release.get("manifestUrl")
                    and _sha256(expected_hash) and hashlib.sha256(data).hexdigest() != expected_hash):
                raise AudioPackError("downloaded audio pack manifest failed checksum validation")
            raw = json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise AudioPackError(
                    "The audio library is unavailable at this download address (HTTP 404). "
                    "Copy the matching pack-manifest.json and all 16 audio ZIP files into "
                    "PronounceIt's data folder, then retry."
                ) from exc
            raise AudioPackError(f"could not download audio pack manifest: {exc}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.URLError) as exc:
            raise AudioPackError(f"could not download audio pack manifest: {exc}") from exc
        return validate_manifest(raw)

    def _manifest_for_version(self, version: str) -> dict[str, Any] | None:
        if not is_supported_pack_version(version):
            return None
        path = self.pack_root / version / "pack-manifest.json"
        try:
            stamp = path.stat()
            cache = self._manifest_cache
            if cache and cache[:3] == (path, stamp.st_mtime_ns, stamp.st_size):
                return cache[3]
            manifest = validate_manifest(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, AudioPackError):
            return None
        if str(manifest["packVersion"]).strip() == version:
            self._manifest_cache = (path, stamp.st_mtime_ns, stamp.st_size, manifest)
            return manifest
        return None

    def _legacy_target_manifest(self, active_version: str) -> dict[str, Any] | None:
        active = self._manifest_for_version(active_version)
        if active and self._dictionary_is_compatible(active):
            return active
        # Early libraries lack a release tag. Discover a compatible partial
        # download using its manifest instead of ordering arbitrary version IDs.
        for path in self.pack_root.glob("*/pack-manifest.json"):
            manifest = self._manifest_for_version(path.parent.name)
            if manifest and self._dictionary_is_compatible(manifest):
                return manifest
        return active

    def _active_manifest(self) -> dict[str, Any] | None:
        release = read_release_metadata(self.addon_root)
        expected_version = self._configured_version(release)
        active_version = self._local_state_version()
        if not active_version or (expected_version and active_version != expected_version):
            return None
        manifest = self._manifest_for_version(active_version)
        return manifest if manifest and self._dictionary_is_compatible(manifest, release) else None

    def _local_state_version(self) -> str:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            version = str(state.get("packVersion") or "").strip()
            return version if is_supported_pack_version(version) else ""
        except (OSError, UnicodeError, AttributeError, json.JSONDecodeError):
            return ""

    def _dictionary_is_compatible(self, manifest: dict[str, Any], release: dict[str, Any] | None = None) -> bool:
        try:
            stat = self.dictionary_path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            dictionary_cache = self._dictionary_cache
            if not dictionary_cache or stamp != dictionary_cache[0]:
                dictionary_cache = (stamp, dictionary_sha256(self.dictionary_path))
                self._dictionary_cache = dictionary_cache
            if release is None:
                release = read_release_metadata(self.addon_root)
            expected_version = self._configured_version(release)
            if expected_version and str(manifest["packVersion"]).strip() != expected_version:
                return False
            if self.dictionary_path.name == "medical_pronunciations.json":
                return dictionary_cache[1] == manifest["dictionarySha256"]
            compatibility_cache = self._compatibility_cache
            if not compatibility_cache or compatibility_cache[0] is not manifest:
                compatibility_cache = (manifest, manifest_content_sha256(manifest))
                self._compatibility_cache = compatibility_cache
            return (
                dictionary_cache[1] == release.get("audioLibrarySha256")
                and manifest["dictionarySha256"] == release.get("dictionarySha256")
                and compatibility_cache[1] == release.get("packManifestContentSha256")
            )
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
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
        url = "" if urllib.parse.urlparse(self.manifest_url).scheme == "file" else str(shard.get("url") or "")
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
                        self._raise_if_cancelled()
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
            raise AudioPackCancelled("audio pack download cancelled")

    def _write_json_atomic(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temp = Path(output.name)
            try:
                output.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
                output.flush()
                os.fsync(output.fileno())
                output.close()
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)

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
