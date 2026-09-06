"""Generate, verify, and serve the approval-gated ten-term local audio pilot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.audio import mp3_duration_seconds
from pronounceit.audio_pack import audio_asset_id, file_sha256
from pronounceit.dictionary import DATA_FILE, PronunciationDictionary
from scripts.corpus.phoneme_lexicon import render_record, validate_model_input

SPEC = ROOT / "quality/kokoro_pilot/pilot.json"
TEMPLATE = SPEC.parent / "review.html"
DEFAULT_OUTPUT = ROOT / "build/kokoro_pilot/2026-09-05-v3"
MODEL_CACHE = ROOT / "build/kokoro-model-cache"
METHOD_FILES = [
    Path(__file__),
    ROOT / "scripts/corpus/phoneme_lexicon.py",
    SPEC.parent / "requirements.txt",
]


class PilotError(ValueError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_spec(path: Path = SPEC) -> dict[str, Any]:
    spec = read_json(path)
    if spec.get("schemaVersion") != 1 or len(spec.get("terms", [])) != 10:
        raise PilotError("This pilot requires exactly ten terms and schemaVersion 1")
    if spec.get("dialect") != "en-US" or spec.get("phonemeAlphabet") != "arpabet-syllables-v1":
        raise PilotError("Unsupported dialect or pronunciation record format")
    dictionary = PronunciationDictionary.bundled()
    seen = set()
    for term in spec["terms"]:
        payload = dictionary.lookup(term["term"])
        if not payload.get("found") or payload["term"] != term["term"]:
            raise PilotError(f"Pilot term must match its canonical dictionary spelling: {term['term']}")
        identifier = audio_asset_id(term["term"])
        if identifier in seen:
            raise PilotError("Duplicate pilot term")
        seen.add(identifier)
        if not term.get("sources"):
            raise PilotError(f"Missing pronunciation references: {term['term']}")
        render_record(term)
    return spec


def input_binding(spec_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "specSha256": file_sha256(spec_path),
        "dictionarySha256": file_sha256(DATA_FILE),
        "method": spec["method"],
        "methodFiles": {str(p.relative_to(ROOT)): file_sha256(p) for p in METHOD_FILES},
    }


def audio_metadata(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    duration = mp3_duration_seconds(data)
    if not 0.2 <= duration <= 8.0:
        raise PilotError(f"Invalid or out-of-range MP3: {path.name} ({duration:.3f}s)")
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "durationMs": round(duration * 1000)}


def safe_asset_path(output: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or len(path.parts) != 2 or path.parts[0] != "audio" or path.suffix != ".mp3":
        raise PilotError("Invalid pilot asset path")
    return output / path


def verify(output: Path, spec_path: Path = SPEC) -> dict[str, Any]:
    manifest = read_json(output / "pilot-manifest.json")
    spec = load_spec(spec_path)
    if manifest["inputBinding"] != input_binding(spec_path, spec):
        raise PilotError("Pilot inputs or generation method changed; use a new output directory")
    entries = manifest.get("entries", [])
    if len(entries) != 10 or [e["term"] for e in entries] != [e["term"] for e in spec["terms"]]:
        raise PilotError("Pilot term coverage changed")
    for entry, record in zip(entries, spec["terms"]):
        if entry["assetId"] != audio_asset_id(record["term"]):
            raise PilotError("Asset identity changed")
        rendered = render_record(record)
        if any(entry[key] != value for key, value in rendered.items()):
            raise PilotError(f"Pronunciation input changed: {entry['term']}")
        actual = audio_metadata(safe_asset_path(output, entry["audioFile"]))
        if any(entry[key] != value for key, value in actual.items()):
            raise PilotError(f"Audio checksum or metadata changed: {entry['term']}")
    binding = {
        "inputBinding": manifest["inputBinding"],
        "environment": manifest["environment"],
        "modelFiles": manifest["modelFiles"],
        "entries": entries,
    }
    if digest(binding) != manifest["bindingSha256"]:
        raise PilotError("Pilot manifest binding changed")
    return manifest


def empty_review(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "bindingSha256": manifest["bindingSha256"],
        "decisions": [{"assetId": e["assetId"], "decision": "", "note": ""} for e in manifest["entries"]],
        "voiceDecision": "",
        "voiceNote": "",
    }


def validate_review(review: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(review, dict) or review.get("bindingSha256") != manifest["bindingSha256"]:
        raise PilotError("Review belongs to different audio")
    decisions = review.get("decisions")
    expected = {e["assetId"] for e in manifest["entries"]}
    if not isinstance(decisions, list) or len(decisions) != len(expected):
        raise PilotError("Review must contain exactly the pilot terms")
    if any(not isinstance(d, dict) for d in decisions) or {d.get("assetId") for d in decisions} != expected:
        raise PilotError("Review term identities differ")
    choices = {"", "accept", "needs-correction"}
    if review.get("voiceDecision") not in choices:
        raise PilotError("Invalid voice decision")
    if not isinstance(review.get("voiceNote"), str) or len(review["voiceNote"]) > 2000:
        raise PilotError("Invalid voice note")
    for decision in decisions:
        if decision.get("decision") not in choices:
            raise PilotError("Invalid term decision")
        if not isinstance(decision.get("note"), str) or len(decision["note"]) > 2000:
            raise PilotError("Invalid correction note")
    accepted = sum(d["decision"] == "accept" for d in decisions)
    needs_correction = any(d["decision"] == "needs-correction" for d in decisions) or review["voiceDecision"] == "needs-correction"
    approved = accepted == 10 and review["voiceDecision"] == "accept"
    return {
        "acceptedTerms": accepted,
        "reviewedTerms": sum(bool(d["decision"]) for d in decisions),
        "status": "approved" if approved else "needs-correction" if needs_correction else "pending",
        "fullGenerationApproved": approved,
        "releaseReady": False,
    }


def review_status(output: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = output / "review.json"
    return validate_review(read_json(path) if path.exists() else empty_review(manifest), manifest)


def render_page(output: Path, manifest: dict[str, Any]) -> None:
    # JSON in a script element must not be able to close that element.
    encoded = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    page = TEMPLATE.read_text(encoding="utf-8").replace("__PILOT_DATA__", encoded)
    (output / "index.html").write_text(page, encoding="utf-8")


def generate(output: Path, spec_path: Path = SPEC, resume: bool = False) -> dict[str, Any]:
    spec = load_spec(spec_path)
    requested = input_binding(spec_path, spec)
    if output.exists():
        if not resume:
            raise PilotError("Output directory already exists; use --resume or a new --output-dir")
        if read_json(output / "run-inputs.json") != requested:
            raise PilotError("Cannot resume with different inputs; preserve this run and use a new directory")
        if (output / "pilot-manifest.json").exists():
            manifest = verify(output, spec_path)
            render_page(output, manifest)
            return manifest
    else:
        output.mkdir(parents=True)
        atomic_json(output / "run-inputs.json", requested)
        for source in [*METHOD_FILES, spec_path]:
            snapshot = output / "generation-source" / source.relative_to(ROOT)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, snapshot)
    (output / "audio").mkdir(exist_ok=True)

    # Heavy dependencies remain entirely in the separate generation environment.
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_XET_CACHE"] = str(MODEL_CACHE / "xet")
    import numpy as np
    import torch
    import lameenc
    from huggingface_hub import hf_hub_download
    from kokoro import KModel

    method = spec["method"]
    if method["device"] != "cpu" or method["sampleRate"] != 24000:
        raise PilotError("This method is pinned to CPU inference and 24 kHz")
    paths = {}
    for filename in ("config.json", method["modelFile"], f"voices/{method['voice']}.pt"):
        paths[filename] = Path(hf_hub_download(
            repo_id=method["modelRepo"], filename=filename,
            revision=method["modelRevision"], cache_dir=str(MODEL_CACHE),
        ))
    hashes = {name: file_sha256(path) for name, path in paths.items()}
    if hashes[method["modelFile"]] != method["expectedModelSha256"]:
        raise PilotError("Model weights do not match the pinned v1.0 checksum")
    environment = {
        "python": sys.version.split()[0],
        "packages": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
    }
    generation_binding = digest({"inputs": requested, "modelFiles": hashes, "environment": environment})
    config = read_json(paths["config.json"])
    rendered_terms = [render_record(record) for record in spec["terms"]]
    for rendered in rendered_terms:
        validate_model_input(rendered["phonemes"], config["vocab"])
    torch.set_num_threads(4)
    model = None
    voice = None
    dictionary = PronunciationDictionary.bundled()
    entries = []
    started = time.monotonic()
    for position, (record, rendered) in enumerate(zip(spec["terms"], rendered_terms), 1):
        identifier = audio_asset_id(record["term"])
        filename = f"audio/{position:02d}-{identifier[:16]}.mp3"
        path = output / filename
        sidecar = path.with_suffix(".meta.json")
        job_hash = digest({"generation": generation_binding, "record": record, "phonemes": rendered["phonemes"]})
        if path.exists() or sidecar.exists():
            if not path.exists() or not sidecar.exists():
                raise PilotError(f"Incomplete existing asset: {record['term']}; preserve it and use a new run")
            metadata = read_json(sidecar)
            actual = audio_metadata(path)
            if metadata.get("jobSha256") != job_hash or any(metadata.get(k) != v for k, v in actual.items()):
                raise PilotError(f"Existing audio is stale or changed: {record['term']}")
        else:
            if model is None:
                model = KModel(repo_id=method["modelRepo"], config=config, model=str(paths[method["modelFile"]])).eval()
                voice = torch.load(paths[f"voices/{method['voice']}.pt"], map_location="cpu", weights_only=True)
            seed = method["seed"] + int(identifier[:8], 16)
            torch.manual_seed(seed)
            np.random.seed(seed % (2**32))
            with torch.inference_mode():
                waveform = model(
                    rendered["phonemes"], voice[len(rendered["phonemes"]) - 1],
                    speed=method["speed"],
                ).numpy().astype(np.float32)
            if waveform.ndim != 1 or not len(waveform) or not np.isfinite(waveform).all():
                raise PilotError(f"Invalid waveform: {record['term']}")
            peak = float(np.max(np.abs(waveform)))
            if peak < 0.001:
                raise PilotError(f"Silent waveform: {record['term']}")
            waveform *= min(1.0, 0.95 / peak)
            waveform = np.pad(waveform, (1200, 2400))  # 50 ms lead, 100 ms tail; no syllable gaps.
            encoder = lameenc.Encoder()
            encoder.set_bit_rate(method["bitrateKbps"])
            encoder.set_in_sample_rate(method["sampleRate"])
            encoder.set_out_sample_rate(method["sampleRate"])
            encoder.set_channels(1)
            encoder.set_quality(2)
            encoder.silence()
            pcm = (waveform * 32767).round().astype("<i2").tobytes()
            encoded = bytes(encoder.encode(pcm)) + bytes(encoder.flush())
            temporary = path.with_suffix(".mp3.tmp")
            temporary.write_bytes(encoded)
            actual = audio_metadata(temporary)
            metadata = {
                **actual, "jobSha256": job_hash,
                "peak": float(np.max(np.abs(waveform))),
                "rms": float(np.sqrt(np.mean(waveform ** 2))),
                "sampleCount": int(len(waveform)),
            }
            # The sidecar is committed with the output; incomplete commits fail closed.
            os.replace(temporary, path)
            atomic_json(sidecar, metadata)
        entries.append({
            "position": position, "term": record["term"], "assetId": identifier,
            **rendered, **metadata, "audioFile": filename,
            "reason": record["reason"], "note": record.get("note", ""),
            "sources": record["sources"], "referenceConflict": record.get("referenceConflict", False),
            "currentPronunciation": dictionary.lookup(record["term"])["pronunciation"],
            "reviewStatus": "unreviewed",
        })
        print(f"{position}/10 {record['term']} ({metadata['durationMs']} ms)", flush=True)
    binding = {"inputBinding": requested, "environment": environment, "modelFiles": hashes, "entries": entries}
    manifest = {
        "schemaVersion": 1, "pilotId": spec["pilotId"], **binding,
        "bindingSha256": digest(binding),
        "generationSeconds": round(time.monotonic() - started, 2),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "qualityStatus": "awaiting-user-review", "releaseReady": False,
        "productionFilesChanged": False,
    }
    atomic_json(output / "pilot-manifest.json", manifest)
    render_page(output, manifest)
    verify(output, spec_path)
    return manifest


def serve(output: Path, spec_path: Path = SPEC, port: int = 8766) -> None:
    verify(output, spec_path)
    token = secrets.token_urlsafe(32)

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/review":
                if self.headers.get("X-Review-Token") != token:
                    self.send_error(403)
                    return
                manifest = verify(output, spec_path)
                saved = output / "review.json"
                self.json_response(read_json(saved) if saved.exists() else empty_review(manifest))
            elif self.path in {"/", "/index.html"}:
                html = (output / "index.html").read_text(encoding="utf-8").replace("__REVIEW_TOKEN__", token)
                body = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

        def do_POST(self) -> None:
            if self.path != "/review" or self.headers.get("X-Review-Token") != token:
                self.send_error(403)
                return
            if self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 50000:
                    raise PilotError("Invalid review size")
                review = json.loads(self.rfile.read(length))
                manifest = verify(output, spec_path)
                status = validate_review(review, manifest)
                saved = {
                    "bindingSha256": review["bindingSha256"],
                    "decisions": review["decisions"], "voiceDecision": review["voiceDecision"],
                    "voiceNote": review["voiceNote"], "savedAt": datetime.now(timezone.utc).isoformat(),
                }
                atomic_json(output / "review.json", saved)
                self.json_response(status)
            except (ValueError, KeyError, OSError) as exc:
                self.json_response({"error": str(exc)}, 400)

        def json_response(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def list_directory(self, path: str) -> None:
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(output)))
    print(f"Listening page: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "verify", "serve"])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            manifest = generate(args.output_dir, args.spec, args.resume)
        elif args.command == "serve":
            serve(args.output_dir, args.spec, args.port)
            return 0
        else:
            manifest = verify(args.output_dir, args.spec)
        status = review_status(args.output_dir, manifest)
        print(json.dumps({"assetsValid": True, "termCount": len(manifest["entries"]), **status}, indent=2))
        return 2 if args.require_approved and not status["fullGenerationApproved"] else 0
    except (ValueError, KeyError, OSError) as exc:
        print(f"Pilot error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
