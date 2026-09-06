"""Prepare/check/run the approved local audio rebuild. Only 'run' starts bulk synthesis."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from pronounceit.audio_pack import audio_asset_id, file_sha256
from pronounceit.dictionary import DATA_FILE, normalize_term
from scripts.audio.kokoro_pilot import DEFAULT_OUTPUT as PILOT, SPEC, MODEL_CACHE, atomic_json, digest, read_json, verify, review_status, audio_metadata
from scripts.corpus.kokoro_sources import PREPARED, word_coverage_key
from scripts.corpus.phoneme_lexicon import validate_model_input

WORK = ROOT / "build/kokoro-rebuild"
RUN = WORK / "run-2026-09-05"
ENGINE_FILES = [Path(__file__), ROOT / "scripts/audio/kokoro_pack.py", ROOT / "scripts/corpus/kokoro_sources.py",
                ROOT / "scripts/release/build_ankiaddon.py", ROOT / "Start Overnight Audio Rebuild.command"]
STAGE_INPUTS = [ROOT / name for name in ("pronounceit", "web", "data/high_yield_checklist.json",
    "data/medical_pronunciation_lexicon_for_codex.txt", "manifest.json", "config.json", "__init__.py",
    "config.md", "LICENSE", "README.md", "PRONUNCIATION_QA.md", "quality/kokoro_rebuild",
    "user_files/README.txt", "user_files/custom_pronunciations.sample.json")]


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_records() -> list[dict]:
    with (PREPARED / "pronunciations.jsonl").open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def runtime_hashes() -> dict[str, str]:
    files = []
    for source in STAGE_INPUTS:
        if source.is_dir():
            files.extend(p for p in source.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                         and p.name != ".DS_Store" and p.suffix not in {".pyc", ".pyo"})
        else:
            files.append(source)
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in sorted(files)}


def check_prepared(check_runtime: bool = True) -> tuple[dict, dict, list[dict]]:
    pilot = verify(PILOT)
    if not review_status(PILOT, pilot)["fullGenerationApproved"]:
        raise ValueError("Accepted Kokoro pilot is missing or changed")
    prepared = read_json(PREPARED / "prepared.json")
    if prepared["pilotBindingSha256"] != pilot["bindingSha256"]:
        raise ValueError("Prepared inputs use a different pilot")
    if file_sha256(DATA_FILE) != prepared["originalDictionarySha256"]:
        raise ValueError("Current dictionary changed after pronunciation preparation")
    if file_sha256(PREPARED / "pronunciations.jsonl") != prepared["recordsSha256"]:
        raise ValueError("Prepared phoneme records changed")
    if file_sha256(PREPARED / "original-dictionary.json") != prepared["originalDictionarySha256"]:
        raise ValueError("Prepared dictionary snapshot changed")
    for name, current in (("pilot-spec.json", SPEC), ("pilot-manifest.json", PILOT / "pilot-manifest.json"),
                          ("pilot-acceptance.json", PILOT / "acceptance.json")):
        if file_sha256(PREPARED / name) != file_sha256(current):
            raise ValueError(f"Prepared approval evidence changed: {name}")
    records = load_records()
    original = read_json(PREPARED / "original-dictionary.json")["terms"]
    if len(records) != 95902 or [r["term"] for r in records] != [r["term"] for r in original]:
        raise ValueError("Canonical term coverage differs")
    for record, item in zip(records, original):
        if record["assetId"] != audio_asset_id(item["term"]) or record["aliases"] != item.get("aliases", []):
            raise ValueError("A canonical identifier or alias changed")
        if word_coverage_key(" ".join(w["text"] for w in record["words"])) != word_coverage_key(item["term"]):
            raise ValueError("A written word was lost from the pronunciation input")
    for package, expected in pilot["environment"]["packages"].items():
        if importlib.metadata.version(package) != expected:
            raise ValueError(f"Generation dependency changed: {package}")
    if sys.version.split()[0] != pilot["environment"]["python"]:
        raise ValueError("Use the prepared generation environment's Python")
    if check_runtime:
        launch = read_json(WORK / "launch-ready.json")
        expected = {"preparedBindingSha256": prepared["bindingSha256"], "recordsSha256": prepared["recordsSha256"],
                    "engineFiles": {str(p.relative_to(ROOT)): file_sha256(p) for p in ENGINE_FILES}, "runtimeFiles": runtime_hashes()}
        if any(launch.get(k) != v for k, v in expected.items()):
            raise ValueError("Prepared launcher or add-on changed; run the check step again before launching")
    return prepared, pilot, records


class ApprovedEngine:
    """The pilot's inference, seed, voice selection, padding, and encoding unchanged."""
    def __init__(self, pilot: dict) -> None:
        import numpy as np
        import torch
        import lameenc
        from kokoro import KModel
        self.np, self.torch, self.lameenc = np, torch, lameenc
        self.method = pilot["inputBinding"]["method"]
        method = self.method
        directory = MODEL_CACHE / "models--hexgrad--Kokoro-82M/snapshots" / method["modelRevision"]
        paths = {name: directory / name for name in pilot["modelFiles"]}
        for name, path in paths.items():
            if not path.is_file() or file_sha256(path) != pilot["modelFiles"][name]:
                raise ValueError(f"The approved local model asset changed or is missing: {name}")
        self.config = read_json(paths["config.json"])
        torch.set_num_threads(4)
        self.model = KModel(repo_id=method["modelRepo"], config=self.config, model=str(paths[method["modelFile"]])).eval()
        self.voice = torch.load(paths[f"voices/{method['voice']}.pt"], map_location="cpu", weights_only=True)

    def synthesize(self, phonemes: str, asset_id: str) -> bytes:
        np, torch, method = self.np, self.torch, self.method
        validate_model_input(phonemes, self.config["vocab"])
        seed = method["seed"] + int(asset_id[:8], 16)
        torch.manual_seed(seed)
        np.random.seed(seed % (2**32))
        with torch.inference_mode():
            waveform = self.model(phonemes, self.voice[len(phonemes) - 1], speed=method["speed"]).numpy().astype(np.float32)
        if waveform.ndim != 1 or not len(waveform) or not np.isfinite(waveform).all():
            raise ValueError("Invalid waveform")
        peak = float(np.max(np.abs(waveform)))
        if peak < 0.001: raise ValueError("Silent waveform")
        waveform *= min(1.0, 0.95 / peak)
        waveform = np.pad(waveform, (1200, 2400))
        encoder = self.lameenc.Encoder()
        encoder.set_bit_rate(method["bitrateKbps"])
        encoder.set_in_sample_rate(method["sampleRate"])
        encoder.set_out_sample_rate(method["sampleRate"])
        encoder.set_channels(1)
        encoder.set_quality(2)
        encoder.silence()
        pcm = (waveform * 32767).round().astype("<i2").tobytes()
        return bytes(encoder.encode(pcm)) + bytes(encoder.flush())


def validate_decoding(path: Path) -> None:
    # The decoder is a QA dependency, kept outside the approved synthesis environment.
    qa = str(ROOT / "build/kokoro-audio-qa-libs")
    if qa not in sys.path: sys.path.append(qa)
    import soundfile
    import numpy as np
    waveform, rate = soundfile.read(path, dtype="float32")
    if rate != 24000 or waveform.ndim != 1 or not np.isfinite(waveform).all() or not len(waveform):
        raise ValueError(f"MP3 decode failed: {path.name}")
    if float(np.max(np.abs(waveform))) < 0.001:
        raise ValueError(f"Decoded audio is silent: {path.name}")


def pilot_parity(engine: ApprovedEngine, pilot: dict) -> dict:
    output = WORK / "preflight-pilot"
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    for entry in pilot["entries"]:
        encoded = engine.synthesize(entry["phonemes"], entry["assetId"])
        checksum = hashlib.sha256(encoded).hexdigest()
        if checksum != entry["sha256"]:
            raise ValueError(f"Batch engine differs from the accepted pilot: {entry['term']}")
        path = output / (entry["assetId"] + ".mp3")
        path.write_bytes(encoded)
        validate_decoding(path)
        checks.append({"term": entry["term"], "sha256": checksum})
    result = {"pilotBindingSha256": pilot["bindingSha256"], "exactMatches": checks, "checkedAt": utc()}
    atomic_json(output / "parity.json", result)
    return result


def operational_preflight(engine: ApprovedEngine, pilot: dict, prepared: dict, records: list[dict]) -> dict:
    """A bounded trial of difficult lengths, resume, packaging, and pack loading."""
    from scripts.audio.kokoro_pack import candidate_dictionary, stage_addon, write_pack
    from pronounceit.audio_pack import AudioPackManager
    identifiers = {entry["assetId"] for entry in pilot["entries"]}
    by_length = sorted(records, key=lambda r: len(r["phonemes"]))
    identifiers.update(r["assetId"] for r in by_length[:4] + by_length[-8:])
    sources = set()
    for record in records:
        for word in record["words"]:
            kind = word["provenance"]["kind"]
            if kind not in sources:
                sources.add(kind); identifiers.add(record["assetId"])
    selected = [r for r in records if r["assetId"] in identifiers]
    if len(selected) > 40:
        raise ValueError("Preflight unexpectedly exceeds its small sample limit")
    binding = digest({"prepared": prepared["bindingSha256"], "engine": {p.name: file_sha256(p) for p in ENGINE_FILES}})
    directory = WORK / "preflight" / binding[:16]
    started = time.monotonic()
    reports = {r["assetId"]: ensure_asset(r, directory / "audio", binding, engine.synthesize) for r in selected}
    elapsed = time.monotonic() - started
    first = selected[0]
    identifier = first["assetId"]
    (directory / "audio" / f"{identifier}.meta.json").rename(directory / "audio" / f"{identifier}.pending.json")
    (directory / "audio" / f"{identifier}.mp3").rename(directory / "audio" / f"{identifier}.mp3.tmp")
    def forbidden_synthesis(*_):
        raise ValueError("Preflight resume unexpectedly tried to regenerate completed audio")
    ensure_asset(first, directory / "audio", binding, forbidden_synthesis)
    for record in selected:
        ensure_asset(record, directory / "audio", binding, forbidden_synthesis)
    original = read_json(PREPARED / "original-dictionary.json")
    original["terms"] = [item for item in original["terms"] if audio_asset_id(item["term"]) in identifiers]
    method = pilot["inputBinding"]["method"]
    generation = {"provider": "kokoro-local", "model": method["modelRepo"], "modelRevision": method["modelRevision"],
                  "voice": method["voice"], "speed": method["speed"], "bindingSha256": binding}
    terms = {r["term"] for r in selected}
    dictionary = candidate_dictionary(original, selected, reports, terms, generation)
    archive = stage_addon(directory / "addon", dictionary, directory / "audio", terms, selected)
    manifest = write_pack(directory / "pack", directory / "addon/data/medical_pronunciations.json",
                          directory / "audio", selected, reports, generation, prepared, pilot)
    manager = AudioPackManager(directory / "addon", manifest_url=(directory / "pack/pack-manifest.json").as_uri())
    if not manager.download().installed:
        raise ValueError("Preflight pack could not be installed")
    manager = AudioPackManager(directory / "addon")
    for record in selected:
        resolved = manager.resolve(record["term"])
        if not resolved or file_sha256(resolved) != reports[record["assetId"]]["sha256"]:
            raise ValueError("Preflight pack failed after restart")
        validate_decoding(resolved)
    result = {"sampleCount": len(selected), "generationSeconds": round(elapsed, 2),
              "maxDurationMs": max(r["durationMs"] for r in reports.values()),
              "testedLongestPhonemeCount": max(len(r["phonemes"]) for r in selected),
              "sourceKinds": sorted(sources), "interruptedCommitRecovered": True, "completedClipsReused": True,
              "shardsBuiltAndVerified": 16, "packLoadedAfterRestart": True, "addonArchive": str(archive),
              "sampleOnly": True, "bulkRunStarted": False}
    atomic_json(directory / "preflight-report.json", result)
    return result


def check() -> dict:
    prepared, pilot, records = check_prepared(check_runtime=False)
    free = shutil.disk_usage(WORK).free
    if free < 8 * 1024**3: raise ValueError("Keep at least 8 GiB free for audio, shards, and the separate candidate")
    engine = ApprovedEngine(pilot)
    for record in records: validate_model_input(record["phonemes"], engine.config["vocab"])
    parity = pilot_parity(engine, pilot)
    operations = operational_preflight(engine, pilot, prepared, records)
    import resource
    report = {"schemaVersion": 1, "preparedBindingSha256": prepared["bindingSha256"], "recordsSha256": prepared["recordsSha256"],
              "pilotBindingSha256": pilot["bindingSha256"], "pilotExactMatches": len(parity["exactMatches"]),
              "engineFiles": {str(p.relative_to(ROOT)): file_sha256(p) for p in ENGINE_FILES},
              "runtimeFiles": runtime_hashes(), "allInputsValidated": len(records),
              "operationalPreflight": operations,
              "peakProcessMemoryMiB": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2),
              "freeDiskGiB": round(free / 1024**3, 1), "checkedAt": utc(), "bulkRunStarted": False, "releaseReady": False}
    atomic_json(WORK / "launch-ready.json", report)
    return report


def asset_job_hash(record: dict, generation_binding: str) -> str:
    return digest({"generationBinding": generation_binding, "assetId": record["assetId"],
                   "phonemes": record["phonemes"], "phonemeInputSha256": record["phonemeInputSha256"]})


def ensure_asset(record: dict, directory: Path, generation_binding: str, synthesize) -> dict:
    identifier = record["assetId"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{identifier}.mp3"
    sidecar = directory / f"{identifier}.meta.json"
    pending = directory / f"{identifier}.pending.json"
    temporary = directory / f"{identifier}.mp3.tmp"
    job_hash = asset_job_hash(record, generation_binding)
    if sidecar.exists():
        metadata = read_json(sidecar)
        if metadata.get("jobSha256") != job_hash or not path.is_file():
            raise ValueError(f"Stale completed audio: {record['term']}")
        if any(metadata.get(k) != v for k, v in audio_metadata(path).items()):
            raise ValueError(f"Changed completed audio: {record['term']}")
        return metadata
    if pending.exists():
        metadata = read_json(pending)
        if metadata.get("jobSha256") != job_hash:
            raise ValueError(f"Pending audio has changed inputs: {record['term']}")
        recovery = path if path.exists() else temporary
        if recovery.exists() and all(metadata.get(k) == v for k, v in audio_metadata(recovery).items()):
            if recovery == temporary: os.replace(temporary, path)
            os.replace(pending, sidecar)
            return metadata
        raise ValueError(f"Incomplete audio commit is corrupt: {record['term']}")
    if path.exists():
        raise ValueError(f"Existing audio has no matching provenance: {record['term']}")
    # Only an uncommitted temporary file can be replaced after an interrupted inference.
    encoded = synthesize(record["phonemes"], identifier)
    with temporary.open("wb") as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
    metadata = {**audio_metadata(temporary), "jobSha256": job_hash,
                "term": record["term"], "assetId": identifier, "phonemeInputSha256": record["phonemeInputSha256"],
                "reviewStatus": record["reviewStatus"], "clipReviewStatus": record["clipReviewStatus"]}
    validate_decoding(temporary)
    atomic_json(pending, metadata)
    os.replace(temporary, path)
    os.replace(pending, sidecar)
    return metadata


def run() -> dict:
    prepared, pilot, records = check_prepared()
    RUN.mkdir(parents=True, exist_ok=True)
    with (WORK / "rebuild.lock").open("a+") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError("Another rebuild is already running")
        current_priority = os.getpriority(os.PRIO_PROCESS, 0)
        if current_priority < 10:
            os.nice(10 - current_priority)
        if os.getpriority(os.PRIO_PROCESS, 0) < 10:
            raise ValueError("Could not apply the prepared lower CPU priority")
        free = shutil.disk_usage(WORK).free
        if free < 8 * 1024**3: raise ValueError("At least 8 GiB free disk space is required")
        launch = read_json(WORK / "launch-ready.json")
        binding = {"preparedBindingSha256": prepared["bindingSha256"], "recordsSha256": prepared["recordsSha256"],
                   "pilotBindingSha256": pilot["bindingSha256"], "method": pilot["inputBinding"]["method"],
                   "modelFiles": pilot["modelFiles"], "environment": pilot["environment"], "engineFiles": launch["engineFiles"]}
        generation_binding = digest(binding)
        manifest_path = RUN / "run-manifest.json"
        if manifest_path.exists() and read_json(manifest_path)["bindingSha256"] != generation_binding:
            raise ValueError("Existing run uses different inputs; no completed output was changed")
        if not manifest_path.exists():
            atomic_json(manifest_path, {**binding, "bindingSha256": generation_binding, "createdAt": utc()})
        print("Starting approved local rebuild. Press Control-C to stop; launch again to resume.", flush=True)
        print(f"Progress and output: {RUN}", flush=True)
        engine = ApprovedEngine(pilot)
        pilot_parity(engine, pilot)
        started = time.monotonic()
        reports, errors = [], []
        generated_count, generation_seconds = 0, 0.0
        def synthesize(phones: str, identifier: str) -> bytes:
            nonlocal generated_count, generation_seconds
            start = time.monotonic()
            encoded = engine.synthesize(phones, identifier)
            generated_count += 1
            generation_seconds += time.monotonic() - start
            return encoded
        try:
            for position, record in enumerate(records, 1):
                if position % 500 == 1 and shutil.disk_usage(RUN).free < 3 * 1024**3:
                    raise ValueError("Disk space is running low; completed clips are saved for resume")
                try:
                    metadata = ensure_asset(record, RUN / "audio", generation_binding, synthesize)
                    reports.append(metadata)
                except (ValueError, RuntimeError) as exc:
                    errors.append({"term": record["term"], "error": str(exc)})
                    print(f"Needs follow-up: {record['term']}: {exc}", flush=True)
                    if len(errors) >= 20:
                        raise ValueError("Stopped after 20 errors to avoid repeating a systemic failure")
                if position % 100 == 0 or position == len(records):
                    elapsed = time.monotonic() - started
                    progress = {"phase": "generating", "completed": len(reports), "processed": position,
                                "total": len(records), "errors": len(errors), "elapsedSeconds": round(elapsed),
                                "generatedThisSession": generated_count,
                                "estimatedRemainingHours": round(generation_seconds / max(1, generated_count) * (len(records) - position) / 3600, 2),
                                "updatedAt": utc(), "releaseReady": False}
                    atomic_json(RUN / "progress.json", progress)
                    atomic_json(RUN / "errors.json", errors)
                    print(f"{position:,}/{len(records):,} clips checked; {len(errors)} errors; approximately {progress['estimatedRemainingHours']:.1f} hours remaining", flush=True)
        except BaseException as exc:
            atomic_json(RUN / "progress.json", {"phase": "stopped", "completed": len(reports), "total": len(records),
                                               "error": str(exc) or type(exc).__name__, "updatedAt": utc(), "releaseReady": False})
            atomic_json(RUN / "errors.json", errors)
            raise
        atomic_json(RUN / "errors.json", errors)
        if errors:
            atomic_json(RUN / "progress.json", {"phase": "needs-correction", "completed": len(reports), "total": len(records),
                                               "errors": len(errors), "updatedAt": utc(), "releaseReady": False})
            raise ValueError(f"{len(errors)} clips need correction; all successful clips are retained")
        print("All clips generated. Building and verifying the matching candidate and 16 download files…", flush=True)
        from scripts.audio.kokoro_pack import build_candidate
        atomic_json(RUN / "progress.json", {"phase": "packaging", "completed": len(reports), "total": len(records),
                                           "updatedAt": utc(), "releaseReady": False})
        try:
            result = build_candidate(RUN, PREPARED, records, reports, binding)
        except BaseException as exc:
            atomic_json(RUN / "progress.json", {"phase": "packaging-stopped", "completed": len(reports), "total": len(records),
                                               "error": str(exc) or type(exc).__name__, "updatedAt": utc(), "releaseReady": False})
            raise
        atomic_json(RUN / "progress.json", {"phase": "complete", "completed": len(reports), "total": len(records),
                                           "updatedAt": utc(), "releaseReady": False, "candidate": result})
        print(f"Rebuild complete. Candidate and quality report: {RUN / 'release-candidate'}", flush=True)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "ready", "status", "run"])
    args = parser.parse_args()
    try:
        if args.command == "check": result = check()
        elif args.command == "ready":
            prepared, pilot, records = check_prepared()
            result = {"ready": True, "validatedInputs": len(records), "pilotBindingSha256": pilot["bindingSha256"], "bulkRunStarted": False}
        elif args.command == "status":
            result = read_json(RUN / "progress.json") if (RUN / "progress.json").exists() else {"phase": "not-started"}
        else: result = run()
        if args.command != "run": print(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        print("Stopped. Completed clips are saved; use the same launcher to resume.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Rebuild stopped: {exc}\nCompleted files are preserved. See the progress log before retrying.", file=sys.stderr)
        raise SystemExit(1)
