"""Build a separate, matching Kokoro candidate after synthesis has finished."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

from pronounceit.audio_pack import DEFAULT_MANIFEST_URL, audio_asset_id, file_sha256, validate_manifest
from pronounceit.dictionary import audio_slug, normalize_term
from pronounceit.qa import load_checklist
from scripts.audio.kokoro_pilot import atomic_json, digest, read_json

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 1024**3
NOTICES = ROOT / "quality/kokoro_rebuild/ATTRIBUTION.md"


def candidate_dictionary(original: dict, records: list[dict], reports: dict[str, dict],
                         bundled_terms: set[str], generation: dict) -> dict:
    if [r["term"] for r in records] != [r["term"] for r in original["terms"]]:
        raise ValueError("Candidate dictionary has different canonical terms")
    result = deepcopy(original)
    for item, record in zip(result["terms"], records):
        if item.get("aliases", []) != record["aliases"]:
            raise ValueError("Candidate dictionary has different aliases")
        metadata = reports[record["assetId"]]
        item.update(audioProvider="kokoro-local", audioReviewStatus=record["clipReviewStatus"],
                    phonemeInputSha256=record["phonemeInputSha256"],
                    audioMetadata={"sha256": metadata["sha256"], "generationBindingSha256": generation["bindingSha256"],
                                   "pronunciationStatus": record["reviewStatus"]})
        # Old bundled filenames must never select an obsolete recording.
        item.pop("audio_file", None)
        item["audioFile"] = f"audio/{audio_slug(item['term'])}.mp3" if item["term"] in bundled_terms else ""
    result["audioRelease"] = {"schemaVersion": 3, **generation}
    return result


def write_pack(output: Path, dictionary_path: Path, audio: Path, records: list[dict], reports: dict[str, dict],
               generation: dict, prepared: dict, pilot: dict) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    identifiers = [record["assetId"] for record in records]
    if len(set(identifiers)) != len(records) or set(identifiers) != set(reports):
        raise ValueError("Pack asset coverage differs")
    shards = []
    for shard_id in "0123456789abcdef":
        selected = sorted(identifier for identifier in identifiers if identifier.startswith(shard_id))
        path = output / f"audio-{shard_id}.zip"
        temporary = path.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for identifier in selected:
                data = (audio / f"{identifier}.mp3").read_bytes()
                if hashlib.sha256(data).hexdigest() != reports[identifier]["sha256"]:
                    raise ValueError(f"Audio changed before packaging: {identifier}")
                info = zipfile.ZipInfo(f"audio/{identifier}.mp3", date_time=(2026, 9, 5, 0, 0, 0))
                archive.writestr(info, data)
        os.replace(temporary, path)
        shards.append({"id": shard_id, "file": path.name, "sha256": file_sha256(path),
                       "size": path.stat().st_size, "assetCount": len(selected)})
    manifest = {
        "schemaVersion": 3, "packVersion": "3-" + generation["bindingSha256"][:16],
        "dictionarySha256": file_sha256(dictionary_path), "assetCount": len(records),
        "format": "audio-24khz-48kbitrate-mono-mp3", "generation": generation,
        "phonemeInput": {"alphabet": "kokoro-us-v1", "recordsSha256": prepared["recordsSha256"], "termCount": len(records)},
        "review": {"methodApproval": "accepted-kokoro-pilot", "pilotClipCount": 10,
                   "pilotBindingSha256": pilot["bindingSha256"], "libraryListeningAccuracyMeasured": False},
        "assets": {r["assetId"]: {"term": r["term"],
                   "sources": sorted({w["provenance"]["url"] for w in r["words"] if w["provenance"].get("url")}),
                   **{k: reports[r["assetId"]][k] for k in
                   ("sha256", "bytes", "durationMs", "phonemeInputSha256", "reviewStatus", "clipReviewStatus")}} for r in records},
        "attribution": {name: (NOTICES.parent / name).read_text(encoding="utf-8")
                        for name in ("ATTRIBUTION.md", "CMUdict-LICENSE", "Misaki-LICENSE")},
        "totalBytes": sum(shard["size"] for shard in shards), "shards": shards,
    }
    validate_manifest(manifest)
    atomic_json(output / "pack-manifest.json", manifest)
    if manifest["totalBytes"] >= LIMIT:
        raise ValueError("Audio pack exceeds the existing 1 GiB limit. Clips are preserved; encoding was not changed.")
    verify_pack(output, manifest, set(identifiers))
    (output / "SHA256SUMS").write_text("".join(f"{file_sha256(output / name)}  {name}\n" for name in
        ["pack-manifest.json"] + [shard["file"] for shard in shards]), encoding="utf-8")
    return manifest


def verify_pack(output: Path, manifest: dict, expected_ids: set[str]) -> None:
    validate_manifest(manifest)
    found = set()
    for shard in manifest["shards"]:
        path = output / shard["file"]
        if path.stat().st_size != shard["size"] or file_sha256(path) != shard["sha256"]:
            raise ValueError(f"Pack checksum failed: {path.name}")
        with zipfile.ZipFile(path) as archive:
            expected = {f"audio/{identifier}.mp3" for identifier in expected_ids if identifier[0] == shard["id"]}
            if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
                raise ValueError(f"Pack coverage failed: {path.name}")
            for name in archive.namelist():
                identifier = Path(name).stem
                if hashlib.sha256(archive.read(name)).hexdigest() != manifest["assets"][identifier]["sha256"]:
                    raise ValueError(f"Packed clip checksum failed: {identifier}")
                found.add(identifier)
    if found != expected_ids:
        raise ValueError("Pack does not contain exactly the requested terms")


def stage_addon(stage: Path, dictionary: dict, audio: Path, bundled_terms: set[str], records: list[dict]) -> Path:
    from scripts.release.build_ankiaddon import INCLUDE_FILES, ALLOWED_USER_FILES, REQUIRED_ARCHIVE_FILES
    stage.mkdir(parents=True, exist_ok=True)
    for name in INCLUDE_FILES:
        shutil.copy2(ROOT / name, stage / name)
    for name in ("pronounceit", "web"):
        shutil.copytree(ROOT / name, stage / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"))
    for name in ("data/high_yield_checklist.json", "data/medical_pronunciation_lexicon_for_codex.txt", *sorted(ALLOWED_USER_FILES)):
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    atomic_json(stage / "data/medical_pronunciations.json", dictionary)
    release_tag = "audio-pack-v3-" + dictionary["audioRelease"]["bindingSha256"][:16]
    manifest_url = DEFAULT_MANIFEST_URL.rsplit("/audio-pack-v2/", 1)[0] + f"/{release_tag}/pack-manifest.json"
    atomic_json(stage / "data/audio-pack-release.json", {"schemaVersion": 3,
                "manifestUrl": manifest_url, "releaseTag": release_tag, "publicationStatus": "not-published"})
    (stage / "audio").mkdir(exist_ok=True)
    expected_audio = {f"audio/{audio_slug(term)}.mp3" for term in bundled_terms}
    for term in bundled_terms:
        shutil.copy2(audio / f"{audio_asset_id(term)}.mp3", stage / f"audio/{audio_slug(term)}.mp3")
    if {p.relative_to(stage).as_posix() for p in (stage / "audio").iterdir() if p.is_file()} != expected_audio:
        raise ValueError("Candidate contains stale or unexpected bundled audio")
    shutil.copy2(NOTICES, stage / "PRONUNCIATION_ASSET_ATTRIBUTION.md")
    shutil.copytree(NOTICES.parent, stage / "pronunciation_licenses", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("README.md"))
    atomic_json(stage / "data/bundled_audio_provenance.json", [r for r in records if r["term"] in bundled_terms])
    archive_path = stage.parent / "pronounceit-kokoro-candidate.ankiaddon"
    temporary = archive_path.with_suffix(".ankiaddon.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file(): archive.write(path, path.relative_to(stage).as_posix())
    with zipfile.ZipFile(temporary) as archive:
        if not (REQUIRED_ARCHIVE_FILES | expected_audio).issubset(archive.namelist()) or archive.testzip():
            raise ValueError("Candidate add-on archive validation failed")
        for name in expected_audio | {"data/medical_pronunciations.json"}:
            if archive.read(name) != (stage / name).read_bytes():
                raise ValueError(f"Candidate archive mismatch: {name}")
    os.replace(temporary, archive_path)
    return archive_path


def build_candidate(run: Path, prepared_dir: Path, records: list[dict], reports: list[dict], binding: dict) -> dict:
    from scripts.audio.kokoro_rebuild import validate_decoding, check_prepared, runtime_hashes, WORK
    check_prepared()  # Fail if the source add-on changed during the overnight run.
    prepared = read_json(prepared_dir / "prepared.json")
    pilot = read_json(prepared_dir / "pilot-manifest.json")
    original = read_json(prepared_dir / "original-dictionary.json")
    if len(records) != 95902 or len(reports) != 95902:
        raise ValueError("All 95,902 clips are required before building the candidate")
    by_id = {r["assetId"]: r for r in reports}
    if set(by_id) != {r["assetId"] for r in records}:
        raise ValueError("Generated clips do not exactly cover the canonical dictionary")
    pilot_entries = {entry["assetId"]: entry for entry in pilot["entries"]}
    for record in records:
        identifier = record["assetId"]
        metadata = by_id[identifier]
        path = run / "audio" / f"{identifier}.mp3"
        if file_sha256(path) != metadata["sha256"] or record["phonemeInputSha256"] != metadata["phonemeInputSha256"]:
            raise ValueError(f"Audio input or checksum changed: {record['term']}")
        if identifier in pilot_entries and metadata["sha256"] != pilot_entries[identifier]["sha256"]:
            raise ValueError("Generated pilot clip differs from the accepted audio")
        validate_decoding(path)
    index = {normalize_term(term): item["term"] for item in original["terms"]
             for term in (item["term"], *item.get("aliases", []))}
    bundled = {index[normalize_term(term)] for term in load_checklist()}
    if len(bundled) != 155 or len({audio_slug(term) for term in bundled}) != 155:
        raise ValueError("The 155 bundled recordings differ or have colliding filenames")
    method = pilot["inputBinding"]["method"]
    generation = {"provider": "kokoro-local", "model": method["modelRepo"], "modelRevision": method["modelRevision"],
                  "voice": method["voice"], "speed": method["speed"], "bindingSha256": digest(binding),
                  "modelFiles": pilot["modelFiles"], "settings": method, "environment": pilot["environment"]}
    output = run / "release-candidate"
    output.mkdir(exist_ok=True)
    dictionary = candidate_dictionary(original, records, by_id, bundled, generation)
    archive = stage_addon(output / "addon", dictionary, run / "audio", bundled, records)
    manifest = write_pack(output / "audio-pack", output / "addon/data/medical_pronunciations.json",
                          run / "audio", records, by_id, generation, prepared, pilot)
    provenance = output / "pronunciation-provenance"
    provenance.mkdir(exist_ok=True)
    for name in ("prepared.json", "pilot-spec.json", "pilot-manifest.json", "pilot-acceptance.json", "source-variants.json", "unresolved.json"):
        shutil.copy2(prepared_dir / name, provenance / name)
    with (prepared_dir / "pronunciations.jsonl").open("rb") as source, gzip.open(provenance / "pronunciations.jsonl.gz", "wb") as target:
        shutil.copyfileobj(source, target)
    shutil.copy2(NOTICES, provenance / "ATTRIBUTION.md")
    for name in ("CMUdict-LICENSE", "Misaki-LICENSE"):
        shutil.copy2(NOTICES.parent / name, provenance / name)
    source_counts = Counter(word["provenance"]["kind"] for record in records for word in record["words"])
    follow_up = [{"term": record["term"], "word": word["text"], "reason": word["provenance"]["needsReview"]}
                 for record in records for word in record["words"] if word["provenance"].get("needsReview")]
    report = {"schemaVersion": 1, "canonicalTerms": len(records), "aliasesPreserved": True, "writtenGuidesPreserved": True,
              "decodedClips": len(reports), "bundledClips": len(bundled), "shards": 16,
              "pilotClipsListeningAccepted": 10, "qualityCounts": prepared["qualityCounts"], "wordSourceCounts": dict(source_counts),
              "sourceVariantRecords": prepared["acceptedVariantRecords"], "estimatesNeedingFollowUp": follow_up,
              "packBytes": manifest["totalBytes"], "packSizeLimitBytes": LIMIT, "generationBindingSha256": generation["bindingSha256"],
              "archiveSha256": file_sha256(archive), "dictionarySha256": manifest["dictionarySha256"],
              "plannedPublication": read_json(output / "addon/data/audio-pack-release.json"),
              "qualityStatus": "generated-and-validated-awaiting-native-review", "releaseReady": False,
              "unrunGates": ["Disposable Anki: bundled and downloaded audio, custom overrides, fallback, restart",
                             "Whole-library listening accuracy is not measured", "Publication approval"],
              "artifacts": {"addon": str(archive), "packManifest": str(output / "audio-pack/pack-manifest.json"), "provenance": str(provenance)}}
    if runtime_hashes() != read_json(WORK / "launch-ready.json")["runtimeFiles"]:
        raise ValueError("Add-on files changed while the candidate was being built")
    atomic_json(output / "quality-report.json", report)
    (output / "READ-ME-FIRST.md").write_text(
        f"# PronounceIt audio candidate\n\nThe rebuild and file checks are complete. This candidate has not been published.\n\n"
        f"{len(records):,} clips, 155 bundled recordings, 16 download files. The written guides and aliases are preserved.\n\n"
        "The ten pilot recordings were accepted. Other clips have not been individually listened to; source-backed inputs and estimates are separated in quality-report.json.\n\n"
        "The add-on and audio pack must be used together. Native Anki checks and publication approval are still required.\n", encoding="utf-8")
    return report
