from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FILE = ROOT / "data" / "medical_pronunciations.json"
DEFAULT_LEXICON_FILE = ROOT / "data" / "medical_pronunciation_lexicon_for_codex.txt"


def normalize_key(value: str) -> str:
    cleaned = " ".join(value.replace("\u00a0", " ").split())
    cleaned = cleaned.strip(".,;:!?()[]{}<>\"`")
    cleaned = re.sub(r"[\u2010-\u2015-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.casefold()


def parse_source_lexicon(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "|" not in line or line.lower().startswith("term |"):
            continue
        term, pronunciation = [part.strip() for part in line.split("|", 1)]
        if term and pronunciation:
            entries.append((term, pronunciation))
    return entries


def syllables_from_pronunciation(pronunciation: str) -> str:
    return re.split(r"\s+or\s+", pronunciation, maxsplit=1, flags=re.IGNORECASE)[0].lower()


def pronunciation_to_speech_text(pronunciation: str) -> str:
    first = re.split(r"\s+or\s+", pronunciation, maxsplit=1, flags=re.IGNORECASE)[0]
    text = first.lower()
    text = re.sub(r"[-/]", " ", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def merge_lexicon(data_file: Path, lexicon_file: Path) -> dict[str, int]:
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    terms = raw.get("terms", [])
    if not isinstance(terms, list):
        terms = []

    by_key: dict[str, dict[str, Any]] = {}
    for item in terms:
        if not isinstance(item, dict) or not item.get("term"):
            continue
        by_key.setdefault(normalize_key(str(item["term"])), item)
        for alias in item.get("aliases", []):
            by_key.setdefault(normalize_key(str(alias)), item)

    added = 0
    updated = 0
    for term, pronunciation in parse_source_lexicon(lexicon_file):
        key = normalize_key(term)
        item = by_key.get(key)
        if item is None:
            item = {
                "term": term,
                "pronunciation": pronunciation,
                "syllables": syllables_from_pronunciation(pronunciation),
            }
            if re.search(r"\s+or\s+", pronunciation, flags=re.IGNORECASE):
                item["speechText"] = pronunciation_to_speech_text(pronunciation)
            terms.append(item)
            by_key[key] = item
            added += 1
            continue

        if item.get("pronunciation") != pronunciation:
            item["pronunciation"] = pronunciation
            updated += 1
        if not item.get("syllables"):
            item["syllables"] = syllables_from_pronunciation(pronunciation)
        if re.search(r"\s+or\s+", pronunciation, flags=re.IGNORECASE):
            item["speechText"] = pronunciation_to_speech_text(pronunciation)

    raw["terms"] = [ordered_item(item) for item in dedupe_terms(terms)]
    data_file.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"sourceEntries": len(parse_source_lexicon(lexicon_file)), "added": added, "updated": updated, "totalTerms": len(raw["terms"])}


def dedupe_terms(terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in terms:
        key = normalize_key(str(item.get("term", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def ordered_item(item: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for field in ("term", "pronunciation", "syllables", "speechText", "aliases", "source", "notes"):
        value = item.get(field)
        if value not in (None, "", []):
            ordered[field] = value
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge source lexicon pronunciations into bundled data.")
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--lexicon-file", type=Path, default=DEFAULT_LEXICON_FILE)
    args = parser.parse_args()
    result = merge_lexicon(args.data_file, args.lexicon_file)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
