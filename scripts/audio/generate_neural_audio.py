from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.audio import mp3_bytes_have_audio, mp3_duration_seconds
from pronounceit.audio_pack import audio_asset_id, dictionary_sha256
from pronounceit.audio_review import (
    deterministic_review_sample,
    load_review_ledger,
    method_approval_status,
    review_ledger_sha256,
)
from pronounceit.dictionary import DATA_FILE, PronunciationDictionary
from pronounceit.phonetics import build_ssml
from pronounceit.qa import load_checklist


VOICE = "en-US-AvaNeural"
RATE = "-5%"
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MAX_BATCH_INPUTS = 10_000
MAX_BATCH_PAYLOAD_BYTES = 1_900_000
DEFAULT_OUTPUT_DIR = ROOT / "build" / "neural_audio_v2"
DEFAULT_REVIEW_LEDGER = ROOT / "data" / "audio_review_ledger.json"


@dataclass(frozen=True)
class AudioJob:
    index: int
    term: str
    asset_id: str
    quality_tier: str
    sapi_segments: list[dict[str, str]]
    synthesis_strategy: str
    ssml: str
    ssml_sha256: str
    output_path: Path


class AzureSpeechClient:
    def __init__(self, key: str, region: str, retries: int = 4) -> None:
        if not key or not region:
            raise RuntimeError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required")
        self.key = key
        self.region = region
        self.retries = max(1, retries)
        self.endpoint = f"https://{region}.api.cognitive.microsoft.com"

    def synthesize_batch(self, jobs: list[AudioJob]) -> list[bytes]:
        if not jobs:
            return []
        identity = hashlib.sha256(
            "\n".join(job.asset_id + job.ssml for job in jobs).encode("utf-8")
        ).hexdigest()[:24]
        job_id = f"pronounceit-{identity}"
        url = (
            f"{self.endpoint}/texttospeech/batchsyntheses/{job_id}"
            "?api-version=2024-04-01"
        )
        body = {
            "inputKind": "SSML",
            "description": f"PronounceIt neural audio ({len(jobs)} terms)",
            "inputs": [{"content": job.ssml} for job in jobs],
            "properties": {
                "outputFormat": OUTPUT_FORMAT,
                "concatenateResult": False,
                "decompressOutputFiles": False,
                "timeToLiveInHours": 168,
            },
        }
        try:
            self._request_json(url, method="PUT", body=body)
        except urllib.error.HTTPError as exc:
            if exc.code not in {409}:
                raise RuntimeError(f"Azure batch creation failed: HTTP {exc.code}") from exc

        deadline = time.monotonic() + (6 * 60 * 60)
        while True:
            status = self._request_json(url)
            state = str(status.get("status") or "")
            if state == "Succeeded":
                break
            if state in {"Failed", "Cancelled"}:
                raise RuntimeError(f"Azure batch {job_id} {state}: {status.get('error')}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Azure batch {job_id} timed out")
            time.sleep(5)

        result_url = str((status.get("outputs") or {}).get("result") or "")
        if not result_url:
            raise RuntimeError(f"Azure batch {job_id} did not provide a result URL")
        result_zip = self._request_bytes(result_url)
        try:
            with zipfile.ZipFile(io.BytesIO(result_zip)) as archive:
                summary = json.loads(archive.read("summary.json").decode("utf-8"))
                results = summary.get("results", [])
                if len(results) != len(jobs):
                    raise RuntimeError(
                        f"Azure batch returned {len(results)} results for {len(jobs)} inputs"
                    )
                audio: list[bytes] = []
                for item in results:
                    if item.get("status") != "Succeeded":
                        raise RuntimeError(f"Azure input synthesis failed: {item}")
                    filename = str(item.get("audioFileName") or "")
                    data = archive.read(filename)
                    if not mp3_bytes_have_audio(data):
                        raise RuntimeError(f"Azure returned invalid audio: {filename}")
                    audio.append(data)
                return audio
        except (KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            raise RuntimeError(f"Azure batch returned an invalid result archive: {exc}") from exc

    def _request_json(
        self,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        result = self._request_bytes(url, method=method, data=data, content_type="application/json")
        return json.loads(result.decode("utf-8")) if result else {}

    def _request_bytes(
        self,
        url: str,
        method: str = "GET",
        data: bytes | None = None,
        content_type: str = "application/octet-stream",
    ) -> bytes:
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Ocp-Apim-Subscription-Key": self.key,
                "Content-Type": content_type,
                "User-Agent": "PronounceIt-audio-builder/1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    return response.read()
            except urllib.error.HTTPError:
                raise
            except (OSError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(min(8, 2**attempt))
        raise RuntimeError(f"Azure request failed: {last_error}")


def _manual_sapi_segments(item: dict[str, Any], term: str) -> list[dict[str, str]]:
    raw_segments = item.get("sapiSegments") or item.get("sapi_segments")
    if raw_segments:
        if not isinstance(raw_segments, list):
            raise ValueError(f"sapiSegments must be a list: {term}")
        segments: list[dict[str, str]] = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                raise ValueError(f"invalid sapiSegments entry: {term}")
            text = str(raw.get("text") or "").strip()
            sapi = str(raw.get("sapi") or "").strip()
            if not text or not sapi:
                raise ValueError(f"empty sapiSegments entry: {term}")
            segments.append({"text": text, "sapi": sapi})
        return segments
    explicit_sapi = str(item.get("sapiPhonemes") or "").strip()
    if explicit_sapi:
        if len(term.split()) != 1:
            raise ValueError(f"multiword terms must use sapiSegments: {term}")
        return [{"text": term, "sapi": explicit_sapi}]
    return []


def _scope_terms(
    raw_terms: list[dict[str, Any]],
    dictionary: PronunciationDictionary,
    scope: str,
) -> set[str] | None:
    if scope == "all":
        return None
    if scope == "high-yield":
        return {
            str(dictionary.lookup(term).get("term") or term).casefold()
            for term in load_checklist()
        }
    tiers = {
        str(item.get("term") or ""): str(
            dictionary.lookup(str(item.get("term") or "")).get("qualityTier") or "fallback"
        )
        for item in raw_terms
    }
    if scope == "curated":
        return {term.casefold() for term, tier in tiers.items() if tier == "curated"}
    if scope == "generated-sample":
        generated = [term for term, tier in tiers.items() if tier == "generated"]
        return {term.casefold() for term in deterministic_review_sample(generated)}
    raise ValueError(f"unsupported generation scope: {scope}")


def build_jobs(
    data_file: Path = DATA_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    scope: str = "all",
    limit: int = 0,
) -> list[AudioJob]:
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    dictionary = PronunciationDictionary.bundled(data_file=data_file)
    raw_terms = [item for item in raw.get("terms", []) if isinstance(item, dict)]
    selected = _scope_terms(raw_terms, dictionary, scope)
    jobs: list[AudioJob] = []
    for item in raw_terms:
        term = str(item.get("term") or "").strip()
        if not term or (selected is not None and term.casefold() not in selected):
            continue
        payload = dictionary.lookup(term)
        quality_tier = str(payload.get("qualityTier") or "fallback")
        segments = _manual_sapi_segments(item, term)
        synthesis_strategy = "manual-sapi" if segments else "azure-native"
        segment_pairs = [(segment["text"], segment["sapi"]) for segment in segments]
        asset_id = audio_asset_id(term)
        ssml = build_ssml(term, segment_pairs, voice=VOICE, rate=RATE)
        jobs.append(
            AudioJob(
                index=len(jobs),
                term=term,
                asset_id=asset_id,
                quality_tier=quality_tier,
                sapi_segments=segments,
                synthesis_strategy=synthesis_strategy,
                ssml=ssml,
                ssml_sha256=hashlib.sha256(ssml.encode("utf-8")).hexdigest(),
                output_path=output_dir / f"{asset_id}.mp3",
            )
        )
        if limit and len(jobs) >= limit:
            break
    return jobs


def _report(
    job: AudioJob,
    data: bytes,
    status: str,
    review_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audio_sha256 = hashlib.sha256(data).hexdigest()
    return {
        "index": job.index,
        "term": job.term,
        "assetId": job.asset_id,
        "qualityTier": job.quality_tier,
        "sapiSegments": job.sapi_segments,
        "synthesisStrategy": job.synthesis_strategy,
        "ssmlSha256": job.ssml_sha256,
        "audioReviewStatus": "method-approved" if review_ledger else "unapproved",
        "bytes": len(data),
        "durationMs": round(mp3_duration_seconds(data) * 1000),
        "sha256": audio_sha256,
        "status": status,
    }


def _metadata(job: AudioJob, data: bytes) -> dict[str, Any]:
    return {
        "assetId": job.asset_id,
        "term": job.term,
        "audioSha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "durationMs": round(mp3_duration_seconds(data) * 1000),
        "ssmlSha256": job.ssml_sha256,
        "synthesisStrategy": job.synthesis_strategy,
        "provider": "azure-speech",
        "voice": VOICE,
        "rate": RATE,
        "outputFormat": OUTPUT_FORMAT,
    }


def _write_metadata(job: AudioJob, data: bytes) -> None:
    metadata_path = job.output_path.with_suffix(".meta.json")
    metadata_temp = metadata_path.with_suffix(".json.tmp")
    metadata_temp.write_text(
        json.dumps(_metadata(job, data), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(metadata_temp, metadata_path)


def generate(
    jobs: list[AudioJob],
    client: AzureSpeechClient,
    workers: int = 8,
    force: bool = False,
    review_ledger: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    pending: list[AudioJob] = []
    for job in jobs:
        metadata_path = job.output_path.with_suffix(".meta.json")
        if not force and job.output_path.is_file() and metadata_path.is_file():
            data = job.output_path.read_bytes()
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
            if (
                mp3_bytes_have_audio(data)
                and metadata.get("ssmlSha256") == job.ssml_sha256
                and metadata.get("synthesisStrategy") == job.synthesis_strategy
            ):
                _write_metadata(job, data)
                reports.append(_report(job, data, "skipped", review_ledger))
                continue
        pending.append(job)

    batches = _job_batches(pending)

    def synthesize_batch(batch: list[AudioJob]) -> list[dict[str, Any]]:
        audio_results = client.synthesize_batch(batch)
        if len(audio_results) != len(batch):
            raise RuntimeError("Azure batch result count did not match input count")
        batch_reports: list[dict[str, Any]] = []
        for job, data in zip(batch, audio_results):
            job.output_path.parent.mkdir(parents=True, exist_ok=True)
            temp = job.output_path.with_suffix(".mp3.tmp")
            temp.write_bytes(data)
            os.replace(temp, job.output_path)
            _write_metadata(job, data)
            batch_reports.append(_report(job, data, "generated", review_ledger))
        return batch_reports

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        futures = [executor.submit(synthesize_batch, batch) for batch in batches]
        for future in as_completed(futures):
            reports.extend(future.result())
    return sorted(reports, key=lambda item: item["index"])


def _job_batches(jobs: list[AudioJob]) -> list[list[AudioJob]]:
    batches: list[list[AudioJob]] = []
    current: list[AudioJob] = []
    current_bytes = 256
    for job in jobs:
        input_bytes = len(json.dumps({"content": job.ssml}).encode("utf-8")) + 1
        if current and (
            len(current) >= MAX_BATCH_INPUTS
            or current_bytes + input_bytes > MAX_BATCH_PAYLOAD_BYTES
        ):
            batches.append(current)
            current = []
            current_bytes = 256
        current.append(job)
        current_bytes += input_bytes
    if current:
        batches.append(current)
    return batches


def write_manifests(
    jobs: list[AudioJob],
    reports: list[dict[str, Any]],
    output_dir: Path,
    data_file: Path,
    review_ledger_path: Path,
) -> None:
    report_path = output_dir / "generation-report.jsonl"
    report_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in reports),
        encoding="utf-8",
    )
    manifest = {
        "schemaVersion": 2,
        "provider": "azure-speech",
        "voice": VOICE,
        "rate": RATE,
        "outputFormat": OUTPUT_FORMAT,
        "dictionarySha256": dictionary_sha256(data_file),
        "terms": len(jobs),
        "billableTermCharacters": sum(len(job.term) for job in jobs),
        "batchSize": MAX_BATCH_INPUTS,
        "batches": len(_job_batches(jobs)),
        "maxBatchPayloadBytes": MAX_BATCH_PAYLOAD_BYTES,
        "synthesisStrategyCounts": {
            strategy: sum(job.synthesis_strategy == strategy for job in jobs)
            for strategy in ("azure-native", "manual-sapi")
        },
        "reviewLedgerSha256": review_ledger_sha256(review_ledger_path),
    }
    (output_dir / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_pilot_terms(data_file: Path) -> list[str]:
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    dictionary = PronunciationDictionary.bundled(data_file=data_file)
    high_yield = {
        str(dictionary.lookup(term).get("term") or term)
        for term in load_checklist()
        if dictionary.lookup(term).get("found")
    }
    curated: list[str] = []
    generated: list[str] = []
    for item in raw.get("terms", []):
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        tier = str(dictionary.lookup(term).get("qualityTier") or "fallback")
        if tier == "curated":
            curated.append(term)
        elif tier == "generated":
            generated.append(term)
    return sorted(high_yield | set(curated) | set(deterministic_review_sample(generated)), key=str.casefold)


def build_pilot_binding(
    data_file: Path,
    output_dir: Path,
    require_complete: bool = True,
) -> dict[str, Any]:
    jobs = {job.term.casefold(): job for job in build_jobs(data_file, output_dir)}
    assets: list[dict[str, str]] = []
    missing: list[str] = []
    for term in _required_pilot_terms(data_file):
        job = jobs[term.casefold()]
        path = job.output_path
        metadata_path = path.with_suffix(".meta.json")
        if not path.is_file() or not mp3_bytes_have_audio(path.read_bytes()):
            missing.append(term)
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing.append(term)
            continue
        if (
            metadata.get("assetId") != job.asset_id
            or metadata.get("ssmlSha256") != job.ssml_sha256
            or metadata.get("synthesisStrategy") != job.synthesis_strategy
        ):
            missing.append(term)
            continue
        assets.append(
            {
                "assetId": job.asset_id,
                "audioSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "ssmlSha256": job.ssml_sha256,
            }
        )
    if require_complete and missing:
        raise SystemExit(
            "Full v2 generation is blocked until the method-approval pilot is complete: "
            f"missing_or_stale={len(missing)} examples={missing[:10]}"
        )
    return {
        "dictionarySha256": dictionary_sha256(data_file),
        "voice": VOICE,
        "rate": RATE,
        "outputFormat": OUTPUT_FORMAT,
        "pilotAssetCount": len(assets),
        "pilotAssets": sorted(assets, key=lambda item: item["assetId"]),
    }


def assert_full_generation_ready(
    data_file: Path,
    output_dir: Path,
    review_ledger: dict[str, Any],
) -> dict[str, Any]:
    binding = build_pilot_binding(data_file, output_dir)
    status = method_approval_status(review_ledger, binding)
    if status != "method-approved":
        raise SystemExit(
            "Full v2 generation is blocked until the checksum-bound Azure-native "
            f"method approval is current: status={status}"
        )
    return binding


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fluent neural pronunciation audio.")
    parser.add_argument("--data-file", type=Path, default=DATA_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--scope",
        choices=("high-yield", "curated", "generated-sample", "all"),
        default="all",
    )
    parser.add_argument("--high-yield", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--review-ledger", type=Path, default=DEFAULT_REVIEW_LEDGER)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        raw = json.loads(args.data_file.read_text(encoding="utf-8"))
        scope = "high-yield" if args.high_yield else args.scope
        terms = [job.term for job in build_jobs(args.data_file, args.output_dir, scope=scope)]
        if args.limit:
            terms = terms[: max(0, args.limit)]
        summary = {
            "terms": len(terms),
            "billableTermCharacters": sum(len(term) for term in terms),
            "minimumBatches": math.ceil(len(terms) / MAX_BATCH_INPUTS),
            "maxInputsPerBatch": MAX_BATCH_INPUTS,
            "maxBatchPayloadBytes": MAX_BATCH_PAYLOAD_BYTES,
            "voice": VOICE,
            "outputFormat": OUTPUT_FORMAT,
            "scope": scope,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    scope = "high-yield" if args.high_yield else args.scope
    review_ledger = load_review_ledger(args.review_ledger)
    approved = False
    if scope == "all":
        assert_full_generation_ready(args.data_file, args.output_dir, review_ledger)
        approved = True
    jobs = build_jobs(
        data_file=args.data_file,
        output_dir=args.output_dir,
        scope=scope,
        limit=max(0, args.limit),
    )
    summary = {
        "terms": len(jobs),
        "billableTermCharacters": sum(len(job.term) for job in jobs),
        "batches": len(_job_batches(jobs)),
        "voice": VOICE,
        "outputFormat": OUTPUT_FORMAT,
    }
    client = AzureSpeechClient(
        os.environ.get("AZURE_SPEECH_KEY", ""),
        os.environ.get("AZURE_SPEECH_REGION", ""),
    )
    reports = generate(
        jobs,
        client,
        workers=args.workers,
        force=args.force,
        review_ledger=review_ledger if approved else None,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_manifests(jobs, reports, args.output_dir, args.data_file, args.review_ledger)
    print(json.dumps({**summary, "generated": len(reports)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
