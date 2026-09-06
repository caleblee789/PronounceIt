from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.audio_pack import audio_asset_id
from pronounceit.dictionary import DATA_FILE, PronunciationDictionary


DEFAULT_SPEC = ROOT / "quality" / "pro_voice_pilot" / "pilot.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pro_voice_pilot"
SCORES_FILENAME = "pro-voice-pilot-scores.csv"
MANIFEST_FILENAME = "pilot-manifest.json"
SUMMARY_FILENAME = "pilot-summary.json"
CSV_FIELDS = (
    "session",
    "position",
    "category",
    "term",
    "current_pronunciation",
    "azure_audio_reference",
    "pro_accuracy",
    "pro_naturalness",
    "azure_accuracy",
    "azure_naturalness",
    "pro_serious_error",
    "notes",
)


class PilotError(ValueError):
    pass


@dataclass(frozen=True)
class PilotTerm:
    session: int
    position: int
    category: str
    term: str
    current_pronunciation: str
    azure_audio_reference: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_spec(path: Path = DEFAULT_SPEC) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotError(f"Could not read pilot specification: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise PilotError("Pilot specification must use schemaVersion 1.")
    sessions = raw.get("sessions")
    terms_per_session = raw.get("termsPerSession")
    if not isinstance(sessions, list) or len(sessions) != 6:
        raise PilotError("Pilot specification must contain exactly six sessions.")
    if terms_per_session != 10:
        raise PilotError("Pilot specification must use ten terms per session.")
    minimum = raw.get("minimumProWinRate")
    if not isinstance(minimum, (int, float)) or not 0 < float(minimum) <= 1:
        raise PilotError("minimumProWinRate must be between 0 and 1.")
    return raw


def resolve_terms(
    spec: dict[str, Any],
    dictionary: PronunciationDictionary | None = None,
) -> list[PilotTerm]:
    dictionary = dictionary or PronunciationDictionary.bundled()
    expected_session_ids = list(range(1, 7))
    actual_session_ids = [session.get("id") for session in spec["sessions"]]
    if actual_session_ids != expected_session_ids:
        raise PilotError("Session identifiers must be ordered from 1 through 6.")

    seen: set[str] = set()
    resolved: list[PilotTerm] = []
    for session in spec["sessions"]:
        category = str(session.get("category") or "").strip()
        terms = session.get("terms")
        if not category or not isinstance(terms, list) or len(terms) != 10:
            raise PilotError(f"Session {session.get('id')} must contain a category and ten terms.")
        for position, requested_term in enumerate(terms, start=1):
            requested = str(requested_term or "").strip()
            payload = dictionary.lookup(requested)
            if not requested or not payload.get("found"):
                raise PilotError(f"Unknown dictionary term in pilot: {requested or '(empty)'}")
            canonical = str(payload.get("term") or requested).strip()
            key = canonical.casefold()
            if key in seen:
                raise PilotError(f"Duplicate canonical pilot term: {canonical}")
            seen.add(key)
            audio_file = str(payload.get("audioFile") or "").strip()
            audio_reference = audio_file or f"offline-pack:{audio_asset_id(canonical)}.mp3"
            resolved.append(
                PilotTerm(
                    session=int(session["id"]),
                    position=position,
                    category=category,
                    term=canonical,
                    current_pronunciation=str(payload.get("pronunciation") or "").strip(),
                    azure_audio_reference=audio_reference,
                )
            )
    if len(resolved) != 60:
        raise PilotError("Pilot must resolve to exactly 60 unique canonical terms.")
    return resolved


def session_prompt(spec: dict[str, Any], session: dict[str, Any]) -> str:
    numbered_terms = "\n".join(
        f"{index}. {term}" for index, term in enumerate(session["terms"], start=1)
    )
    return (
        "Pronounce the 10 medical terms below using common U.S. medical pronunciation. "
        "Say each term once, in the exact order shown, with a clear two-second pause between "
        "terms. Say only the terms: do not speak the numbers, define them, spell them, explain "
        "them, or add an introduction or conclusion. Use your normal speaking speed.\n\n"
        f"{numbered_terms}\n"
    )


def _write_scores(path: Path, terms: Iterable[PilotTerm]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in terms:
            writer.writerow(
                {
                    "session": item.session,
                    "position": item.position,
                    "category": item.category,
                    "term": item.term,
                    "current_pronunciation": item.current_pronunciation,
                    "azure_audio_reference": item.azure_audio_reference,
                    "pro_accuracy": "",
                    "pro_naturalness": "",
                    "azure_accuracy": "",
                    "azure_naturalness": "",
                    "pro_serious_error": "",
                    "notes": "",
                }
            )


def prepare(
    spec_path: Path = DEFAULT_SPEC,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    spec = load_spec(spec_path)
    terms = resolve_terms(spec)
    if output_dir.exists():
        raise PilotError(
            f"Refusing to overwrite existing pilot directory: {output_dir}. "
            "Choose a different --output-dir."
        )
    output_dir.mkdir(parents=True)
    _write_scores(output_dir / SCORES_FILENAME, terms)
    prompt_files: list[str] = []
    for session in spec["sessions"]:
        filename = f"session-{int(session['id']):02d}-prompt.txt"
        (output_dir / filename).write_text(session_prompt(spec, session), encoding="utf-8")
        prompt_files.append(filename)

    manifest = {
        "schemaVersion": 1,
        "pilotId": spec["pilotId"],
        "specSha256": file_sha256(spec_path),
        "dictionarySha256": file_sha256(DATA_FILE),
        "voice": spec["voice"],
        "language": spec["language"],
        "intelligence": spec["intelligence"],
        "termCount": len(terms),
        "sessionCount": len(spec["sessions"]),
        "minimumProWinRate": spec["minimumProWinRate"],
        "requiredProWins": math.ceil(len(terms) * float(spec["minimumProWinRate"])),
        "scoresFile": SCORES_FILENAME,
        "promptFiles": prompt_files,
        "productionFilesChanged": False,
        "disposition": "evaluation-only",
    }
    (output_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _score(value: str, field: str, term: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PilotError(f"{term}: {field} must be an integer from 1 to 5.") from exc
    if not 1 <= parsed <= 5:
        raise PilotError(f"{term}: {field} must be an integer from 1 to 5.")
    return parsed


def _load_score_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise PilotError("The score sheet columns were changed or reordered.")
            return list(reader)
    except OSError as exc:
        raise PilotError(f"Could not read score sheet: {exc}") from exc


def summarize(
    spec_path: Path = DEFAULT_SPEC,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    scores_path: Path | None = None,
) -> dict[str, Any]:
    spec = load_spec(spec_path)
    expected_terms = resolve_terms(spec)
    manifest_path = output_dir / MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotError(f"Missing or invalid pilot manifest: {exc}") from exc
    if (
        manifest.get("specSha256") != file_sha256(spec_path)
        or manifest.get("dictionarySha256") != file_sha256(DATA_FILE)
        or manifest.get("pilotId") != spec.get("pilotId")
    ):
        raise PilotError("Pilot manifest does not match the current specification or dictionary.")

    path = scores_path or output_dir / SCORES_FILENAME
    rows = _load_score_rows(path)
    if len(rows) != len(expected_terms):
        raise PilotError(f"Score sheet must contain exactly {len(expected_terms)} rows.")

    pro_wins = azure_wins = ties = serious_errors = 0
    results: list[dict[str, Any]] = []
    for expected, row in zip(expected_terms, rows):
        identity = (
            str(expected.session),
            str(expected.position),
            expected.category,
            expected.term,
            expected.current_pronunciation,
            expected.azure_audio_reference,
        )
        actual = tuple(row[field] for field in CSV_FIELDS[:6])
        if actual != identity:
            raise PilotError(f"Score sheet identity fields changed near term: {expected.term}")
        pro_accuracy = _score(row["pro_accuracy"], "pro_accuracy", expected.term)
        pro_naturalness = _score(row["pro_naturalness"], "pro_naturalness", expected.term)
        azure_accuracy = _score(row["azure_accuracy"], "azure_accuracy", expected.term)
        azure_naturalness = _score(row["azure_naturalness"], "azure_naturalness", expected.term)
        serious = row["pro_serious_error"].strip().casefold()
        if serious not in {"yes", "no"}:
            raise PilotError(f"{expected.term}: pro_serious_error must be yes or no.")
        serious_errors += serious == "yes"
        pro_total = pro_accuracy + pro_naturalness
        azure_total = azure_accuracy + azure_naturalness
        if pro_accuracy >= 4 and pro_total > azure_total:
            winner = "pro"
            pro_wins += 1
        elif azure_total > pro_total or pro_accuracy < 4:
            winner = "azure"
            azure_wins += 1
        else:
            winner = "tie"
            ties += 1
        results.append(
            {
                "term": expected.term,
                "winner": winner,
                "proAccuracy": pro_accuracy,
                "proNaturalness": pro_naturalness,
                "azureAccuracy": azure_accuracy,
                "azureNaturalness": azure_naturalness,
                "proSeriousError": serious == "yes",
                "notes": row["notes"].strip(),
            }
        )

    required_wins = math.ceil(len(rows) * float(spec["minimumProWinRate"]))
    passed = pro_wins >= required_wins and serious_errors == 0
    summary = {
        "schemaVersion": 1,
        "pilotId": spec["pilotId"],
        "status": "passed" if passed else "failed",
        "decision": "eligible-for-speech-api-pilot" if passed else "retain-azure",
        "reviewedTerms": len(rows),
        "proWins": pro_wins,
        "azureWins": azure_wins,
        "ties": ties,
        "proWinRate": round(pro_wins / len(rows), 4),
        "requiredProWins": required_wins,
        "proSeriousErrors": serious_errors,
        "productionAudioApproved": False,
        "results": results,
    }
    (output_dir / SUMMARY_FILENAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and summarize the evaluation-only ChatGPT Pro Voice pilot."
    )
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--scores", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.spec, args.output_dir)
        else:
            result = summarize(args.spec, args.output_dir, args.scores)
    except PilotError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
