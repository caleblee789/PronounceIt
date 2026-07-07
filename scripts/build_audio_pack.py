from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.audio import mp3_bytes_have_audio, mp3_duration_seconds
from pronounceit.audio_pack import (
    AudioPackError,
    audio_asset_id,
    dictionary_sha256,
    file_sha256,
    is_supported_pack_version,
    validate_manifest,
)
from pronounceit.audio_review import (
    load_review_ledger,
    method_approval_status,
    review_ledger_sha256,
)
from pronounceit.dictionary import DATA_FILE, PronunciationDictionary, audio_slug
from pronounceit.qa import load_checklist
from scripts.generate_neural_audio import build_pilot_binding


DEFAULT_AUDIO_DIR = ROOT / "build" / "neural_audio_v2"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "audio_pack_v2"
DEFAULT_REVIEW_LEDGER = ROOT / "data" / "audio_review_ledger.json"
SHARD_IDS = "0123456789abcdef"


def load_terms(data_file: Path) -> list[str]:
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    return [
        str(item.get("term") or "").strip()
        for item in raw.get("terms", [])
        if isinstance(item, dict) and str(item.get("term") or "").strip()
    ]


def load_generation_report(audio_dir: Path) -> dict[str, dict[str, Any]]:
    path = audio_dir / "generation-report.jsonl"
    if not path.is_file():
        raise SystemExit("Missing v2 generation report; refusing to build audio pack.")
    reports: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        term = str(item.get("term") or "").strip()
        if term:
            reports[term.casefold()] = item
    return reports


def verify_pack(
    data_file: Path = DATA_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    try:
        manifest = validate_manifest(
            json.loads((output_dir / "pack-manifest.json").read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValueError, AudioPackError) as exc:
        raise SystemExit(f"Invalid pack manifest: {exc}") from exc
    terms = load_terms(data_file)
    expected_assets = {audio_asset_id(term) for term in terms}
    if len(expected_assets) != len(terms):
        raise SystemExit("Dictionary does not produce unique audio asset identifiers.")
    actual_assets: set[str] = set()
    total_bytes = 0
    for shard in manifest["shards"]:
        path = output_dir / str(shard["file"])
        if (
            not path.is_file()
            or path.stat().st_size != int(shard["size"])
            or file_sha256(path) != str(shard["sha256"]).casefold()
        ):
            raise SystemExit(f"Shard verification failed: {shard['id']}")
        total_bytes += path.stat().st_size
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if len(names) != int(shard.get("assetCount") or 0):
                    raise SystemExit(f"Shard asset count mismatch: {shard['id']}")
                for name in names:
                    if (
                        not name.startswith("audio/")
                        or not name.endswith(".mp3")
                        or len(name) != len("audio/") + 64 + len(".mp3")
                    ):
                        raise SystemExit(f"Invalid shard member: {name}")
                    asset_id = name[len("audio/") : -len(".mp3")]
                    if asset_id[0] != shard["id"] or asset_id in actual_assets:
                        raise SystemExit(f"Invalid or duplicate shard asset: {asset_id}")
                    if not mp3_bytes_have_audio(archive.read(name)):
                        raise SystemExit(f"Invalid MP3 in shard: {asset_id}")
                    actual_assets.add(asset_id)
        except zipfile.BadZipFile as exc:
            raise SystemExit(f"Invalid shard ZIP: {shard['id']}") from exc
    if actual_assets != expected_assets:
        raise SystemExit(
            "Pack asset set mismatch: "
            f"missing={len(expected_assets - actual_assets)} "
            f"extra={len(actual_assets - expected_assets)}"
        )
    if total_bytes != manifest.get("totalBytes") or total_bytes >= 1024 * 1024 * 1024:
        raise SystemExit("Pack total size is invalid.")
    sums_path = output_dir / "SHA256SUMS"
    expected_sum_lines = [
        f"{file_sha256(output_dir / filename)}  {filename}"
        for filename in ["pack-manifest.json"]
        + sorted(str(shard["file"]) for shard in manifest["shards"])
    ]
    try:
        actual_sum_lines = sums_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SystemExit(f"Missing SHA256SUMS: {exc}") from exc
    if actual_sum_lines != expected_sum_lines:
        raise SystemExit("SHA256SUMS does not match the pack artifacts.")
    return {
        "packVersion": manifest["packVersion"],
        "assetCount": len(actual_assets),
        "shardCount": len(manifest["shards"]),
        "totalBytes": total_bytes,
    }


def validate_release_reviews(
    data_file: Path,
    audio_dir: Path,
    review_ledger_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    reports = load_generation_report(audio_dir)
    ledger = load_review_ledger(review_ledger_path)
    manifest_path = audio_dir / "build-manifest.json"
    try:
        build_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Missing or invalid v2 build manifest: {exc}") from exc
    if (
        build_manifest.get("schemaVersion") != 2
        or build_manifest.get("dictionarySha256") != dictionary_sha256(data_file)
        or build_manifest.get("reviewLedgerSha256") != review_ledger_sha256(review_ledger_path)
    ):
        raise SystemExit("V2 build manifest does not match the dictionary or review ledger.")
    binding = build_pilot_binding(data_file, audio_dir)
    if method_approval_status(ledger, binding) != "method-approved":
        raise SystemExit("Audio method approval is missing, invalid, or stale.")
    terms = load_terms(data_file)
    failures: list[str] = []
    if len(reports) != len(terms):
        failures.append(f"report count mismatch: {len(reports)}/{len(terms)}")
    for term in terms:
        report = reports.get(term.casefold())
        if report is None:
            failures.append(f"missing report: {term}")
            continue
        strategy = str(report.get("synthesisStrategy") or "")
        if strategy not in {"azure-native", "manual-sapi"}:
            failures.append(f"forbidden synthesis strategy: {term}")
        if report.get("phonemes") or strategy == "generated-g2p":
            failures.append(f"generated G2P phonemes: {term}")
        if str(report.get("assetId") or "") != audio_asset_id(term):
            failures.append(f"mismatched asset identifier: {term}")
        if len(str(report.get("ssmlSha256") or "")) != 64:
            failures.append(f"missing SSML hash: {term}")
        asset_id = str(report.get("assetId") or "")
        path = audio_dir / f"{asset_id}.mp3"
        metadata_path = audio_dir / f"{asset_id}.meta.json"
        if not path.is_file():
            failures.append(f"missing audio: {term}")
            continue
        data = path.read_bytes()
        checksum = file_sha256(path)
        duration_ms = round(mp3_duration_seconds(data) * 1000)
        if not mp3_bytes_have_audio(data) or not 200 <= duration_ms <= 8000:
            failures.append(f"invalid audio: {term}")
            continue
        if checksum != str(report.get("sha256") or "").casefold():
            failures.append(f"report checksum mismatch: {term}")
            continue
        if report.get("durationMs") != duration_ms or report.get("bytes") != len(data):
            failures.append(f"report metadata mismatch: {term}")
        if report.get("audioReviewStatus") != "method-approved":
            failures.append(f"audio not method-approved: {term}")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append(f"missing or invalid sidecar: {term}")
            continue
        expected_metadata = {
            "assetId": asset_id,
            "term": term,
            "audioSha256": checksum,
            "bytes": len(data),
            "durationMs": duration_ms,
            "ssmlSha256": report.get("ssmlSha256"),
            "synthesisStrategy": strategy,
            "provider": "azure-speech",
            "voice": "en-US-AvaNeural",
            "rate": "-5%",
            "outputFormat": "audio-24khz-48kbitrate-mono-mp3",
        }
        if metadata != expected_metadata:
            failures.append(f"sidecar metadata mismatch: {term}")
    if failures:
        raise SystemExit(
            "Audio review gate failed; refusing to build v2 pack: "
            f"failures={len(failures)} examples={failures[:10]}"
        )
    return reports, ledger


def build_pack(
    data_file: Path = DATA_FILE,
    audio_dir: Path = DEFAULT_AUDIO_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    pack_version: str = "2",
    base_url: str = "",
    review_ledger_path: Path = DEFAULT_REVIEW_LEDGER,
) -> dict[str, Any]:
    if not is_supported_pack_version(pack_version):
        raise SystemExit("Audio pack version must use the supported version 2 namespace.")
    reports, _ledger = validate_release_reviews(data_file, audio_dir, review_ledger_path)
    terms = load_terms(data_file)
    if len({term.casefold() for term in terms}) != len(terms):
        raise SystemExit("Dictionary contains duplicate normalized terms.")
    missing: list[str] = []
    invalid: list[str] = []
    assets: dict[str, tuple[str, Path]] = {}
    for term in terms:
        asset_id = audio_asset_id(term)
        path = audio_dir / f"{asset_id}.mp3"
        if not path.is_file():
            missing.append(term)
            continue
        data = path.read_bytes()
        duration = mp3_duration_seconds(data)
        if not mp3_bytes_have_audio(data) or not 0.2 <= duration <= 8.0:
            invalid.append(term)
            continue
        if asset_id in assets:
            raise SystemExit(f"Audio asset hash collision: {term}")
        assets[asset_id] = (term, path)
    if missing or invalid:
        raise SystemExit(
            f"Cannot build complete audio pack: missing={len(missing)} invalid={len(invalid)} "
            f"examples={(missing + invalid)[:10]}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    shards: list[dict[str, Any]] = []
    for shard_id in SHARD_IDS:
        filename = f"pronounceit-audio-{pack_version}-{shard_id}.zip"
        path = output_dir / filename
        shard_assets = [
            (asset_id, term, source)
            for asset_id, (term, source) in assets.items()
            if asset_id.startswith(shard_id)
        ]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for asset_id, _term, source in sorted(shard_assets):
                info = zipfile.ZipInfo(f"audio/{asset_id}.mp3", (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes())
        shard_record: dict[str, Any] = {
            "id": shard_id,
            "file": filename,
            "sha256": file_sha256(path),
            "size": path.stat().st_size,
            "assetCount": len(shard_assets),
        }
        if base_url:
            shard_record["url"] = f"{base_url.rstrip('/')}/{filename}"
        shards.append(shard_record)

    manifest = {
        "schemaVersion": 2,
        "packVersion": pack_version,
        "dictionarySha256": dictionary_sha256(data_file),
        "assetCount": len(assets),
        "voice": "en-US-AvaNeural",
        "prosodyRate": "-5%",
        "format": "audio-24khz-48kbitrate-mono-mp3",
        "reviewLedgerSha256": review_ledger_sha256(review_ledger_path),
        "methodApprovalBindingSha256": str(
            (load_review_ledger(review_ledger_path).get("methodApproval") or {}).get(
                "bindingSha256"
            )
            or ""
        ),
        "synthesisStrategyCounts": {
            strategy: sum(
                str(item.get("synthesisStrategy") or "") == strategy
                for item in reports.values()
            )
            for strategy in ("azure-native", "manual-sapi")
        },
        "totalBytes": sum(shard["size"] for shard in shards),
        "shards": shards,
    }
    (output_dir / "pack-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if manifest["totalBytes"] >= 1024 * 1024 * 1024:
        raise SystemExit("Audio pack must be smaller than 1 GiB.")
    checksum_files = ["pack-manifest.json"] + sorted(shard["file"] for shard in shards)
    (output_dir / "SHA256SUMS").write_text(
        "".join(
            f"{file_sha256(output_dir / filename)}  {filename}\n"
            for filename in checksum_files
        ),
        encoding="utf-8",
    )
    verify_pack(data_file, output_dir)
    return manifest


def install_high_yield(
    audio_dir: Path = DEFAULT_AUDIO_DIR,
    destination: Path = ROOT / "audio",
) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    dictionary = PronunciationDictionary.bundled()
    for term in load_checklist():
        canonical_term = str(dictionary.lookup(term).get("term") or term)
        source = audio_dir / f"{audio_asset_id(canonical_term)}.mp3"
        if not source.is_file() or not mp3_bytes_have_audio(source.read_bytes()):
            raise SystemExit(f"Missing valid generated high-yield audio: {term}")
        slug = audio_slug(canonical_term)
        shutil.copy2(source, destination / f"{slug}.mp3")
        (destination / f"{slug}.aiff").unlink(missing_ok=True)
        copied += 1
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the versioned PronounceIt audio pack.")
    parser.add_argument("--data-file", type=Path, default=DATA_FILE)
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pack-version", default="2")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--review-ledger", type=Path, default=DEFAULT_REVIEW_LEDGER)
    parser.add_argument("--install-high-yield", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        print(json.dumps(verify_pack(args.data_file, args.output_dir), indent=2, sort_keys=True))
        return 0
    manifest = build_pack(
        data_file=args.data_file,
        audio_dir=args.audio_dir,
        output_dir=args.output_dir,
        pack_version=args.pack_version,
        base_url=args.base_url,
        review_ledger_path=args.review_ledger,
    )
    if args.install_high_yield:
        manifest["installedHighYield"] = install_high_yield(args.audio_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
