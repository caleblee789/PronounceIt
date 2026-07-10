from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.audio import mp3_bytes_have_audio
from pronounceit.audio_pack import audio_asset_id, file_sha256
from pronounceit.audio_review import (
    load_review_ledger,
    method_approval_status,
    method_binding_sha256,
    review_status,
)
from pronounceit.dictionary import DATA_FILE, PronunciationDictionary
from scripts.audio.generate_neural_audio import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REVIEW_LEDGER,
    _required_pilot_terms,
    build_pilot_binding,
)


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def record_review(
    term: str,
    accuracy: int,
    naturalness: int,
    reviewer: str,
    failure_reason: str,
    correction_status: str,
    audio_dir: Path,
    ledger_path: Path,
) -> dict[str, object]:
    dictionary = PronunciationDictionary.bundled()
    payload = dictionary.lookup(term)
    canonical = str(payload.get("term") or term).strip()
    if not payload.get("found"):
        raise SystemExit(f"Unknown dictionary term: {term}")
    if not 1 <= accuracy <= 5 or not 1 <= naturalness <= 5:
        raise SystemExit("Accuracy and naturalness scores must be between 1 and 5.")
    asset_id = audio_asset_id(canonical)
    path = audio_dir / f"{asset_id}.mp3"
    if not path.is_file() or not mp3_bytes_have_audio(path.read_bytes()):
        raise SystemExit(f"Missing valid v2 pilot audio: {canonical}")
    passed = accuracy >= 4 and naturalness >= 4
    entry: dict[str, object] = {
        "term": canonical,
        "assetId": asset_id,
        "audioSha256": file_sha256(path),
        "accuracy": accuracy,
        "naturalness": naturalness,
        "status": "passed" if passed else "failed",
        "reviewer": reviewer.strip(),
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
        "failureReason": failure_reason.strip(),
        "correctionStatus": correction_status,
    }
    if not entry["reviewer"]:
        raise SystemExit("Reviewer is required.")
    if not passed and not entry["failureReason"]:
        raise SystemExit("A failure reason is required for failed audio.")
    ledger = load_review_ledger(ledger_path)
    ledger["entries"].append(entry)
    write_json_atomic(ledger_path, ledger)
    return entry


def review_summary(
    data_file: Path,
    audio_dir: Path,
    ledger_path: Path,
    include_terms: bool = False,
) -> dict[str, object]:
    ledger = load_review_ledger(ledger_path)
    required = _required_pilot_terms(data_file)
    passed = failed = unreviewed = missing = 0
    rows: list[dict[str, str]] = []
    for term in required:
        asset_id = audio_asset_id(term)
        path = audio_dir / f"{asset_id}.mp3"
        if not path.is_file() or not mp3_bytes_have_audio(path.read_bytes()):
            status = "missing"
            missing += 1
        else:
            status = review_status(ledger, asset_id, file_sha256(path))
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            else:
                unreviewed += 1
        rows.append({"term": term, "assetId": asset_id, "status": status})
    binding = build_pilot_binding(data_file, audio_dir, require_complete=False)
    approval_status = method_approval_status(ledger, binding)
    summary: dict[str, object] = {
        "required": len(required),
        "missing": missing,
        "pilotAssetCount": binding["pilotAssetCount"],
        "methodApprovalStatus": approval_status,
        "readyForFullGeneration": (
            binding["pilotAssetCount"] == len(required)
            and approval_status == "method-approved"
        ),
        "individualReviewCounts": {
            "passed": passed,
            "failed": failed,
            "unreviewed": unreviewed,
        },
    }
    if include_terms:
        summary["terms"] = rows
    return summary


def record_method_approval(
    data_file: Path,
    audio_dir: Path,
    ledger_path: Path,
    reviewer: str,
    statement: str,
) -> dict[str, object]:
    reviewer = reviewer.strip()
    statement = statement.strip()
    if not reviewer:
        raise SystemExit("Reviewer is required.")
    if not statement:
        raise SystemExit("Approval statement is required.")
    binding = build_pilot_binding(data_file, audio_dir)
    approval: dict[str, object] = {
        "status": "method-approved",
        "scope": "synthesis-method",
        "reviewer": reviewer,
        "approvedAt": datetime.now(timezone.utc).isoformat(),
        "statement": statement,
        "reviewScopeNote": (
            "Approval covers the checksum-bound synthesis method and pilot; "
            "it does not claim individual review of every generated clip."
        ),
        "binding": binding,
        "bindingSha256": method_binding_sha256(binding),
    }
    ledger = load_review_ledger(ledger_path)
    ledger["methodApproval"] = approval
    write_json_atomic(ledger_path, ledger)
    return approval


def main() -> int:
    parser = argparse.ArgumentParser(description="Record and audit v2 pronunciation reviews.")
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_REVIEW_LEDGER)
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--term", required=True)
    record.add_argument("--accuracy", required=True, type=int)
    record.add_argument("--naturalness", required=True, type=int)
    record.add_argument("--reviewer", required=True)
    record.add_argument("--failure-reason", default="")
    record.add_argument(
        "--correction-status",
        choices=("not-needed", "needed", "resolved"),
        default="not-needed",
    )
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--details", action="store_true")
    approve = subparsers.add_parser("approve-method")
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--statement", required=True)
    args = parser.parse_args()
    if args.command == "record":
        print(json.dumps(record_review(
            args.term,
            args.accuracy,
            args.naturalness,
            args.reviewer,
            args.failure_reason,
            args.correction_status,
            args.audio_dir,
            args.ledger,
        ), indent=2, sort_keys=True))
    elif args.command == "approve-method":
        print(json.dumps(
            record_method_approval(
                DATA_FILE,
                args.audio_dir,
                args.ledger,
                args.reviewer,
                args.statement,
            ),
            indent=2,
            sort_keys=True,
        ))
    else:
        print(json.dumps(
            review_summary(DATA_FILE, args.audio_dir, args.ledger, args.details),
            indent=2,
            sort_keys=True,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
