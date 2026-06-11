from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.dictionary import PronunciationDictionary, pronunciation_to_speech_text
from scripts.import_source_lexicon import normalize_key, ordered_item


DEFAULT_WORDLIST_FILE = Path("/Users/calebm./Desktop/wordlist.txt")
DEFAULT_DATA_FILE = ROOT / "data" / "medical_pronunciations.json"
DEFAULT_ACCEPTED_FILE = ROOT / "data" / "generated_wordlist_pronunciations.accepted.json"
DEFAULT_EXCLUDED_FILE = ROOT / "data" / "generated_wordlist_pronunciations.excluded.csv"
DEFAULT_NEEDS_REVIEW_FILE = ROOT / "data" / "generated_wordlist_pronunciations.needs_review.csv"
GENERATED_SOURCE = "generated-g2p-en"
GENERATED_NOTES = (
    "Machine-generated with g2p-en from spelling; not source-verified. "
    "Review before relying on this pronunciation for curated medical usage."
)
FALLBACK_GENERATED_NOTES = (
    "Machine-generated fallback from raw spelling because g2p-en returned no usable phones; "
    "not source-verified. Review before relying on this pronunciation for curated medical usage."
)

ARPABET_TO_READABLE = {
    "AA": "ah",
    "AE": "a",
    "AH": "uh",
    "AO": "aw",
    "AW": "ow",
    "AY": "eye",
    "B": "b",
    "CH": "ch",
    "D": "d",
    "DH": "th",
    "EH": "eh",
    "ER": "er",
    "EY": "ay",
    "F": "f",
    "G": "g",
    "HH": "h",
    "IH": "ih",
    "IY": "ee",
    "JH": "j",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ng",
    "OW": "oh",
    "OY": "oy",
    "P": "p",
    "R": "r",
    "S": "s",
    "SH": "sh",
    "T": "t",
    "TH": "th",
    "UH": "oo",
    "UW": "oo",
    "V": "v",
    "W": "w",
    "Y": "y",
    "Z": "z",
    "ZH": "zh",
}
VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
PHONE_RE = re.compile(r"^([A-Z]+)([0-2]?)$")


def load_wordlist(path: Path) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        term = " ".join(line.replace("\u00a0", " ").split())
        key = normalize_key(term)
        if term and key and key not in seen:
            terms.append(term)
            seen.add(key)
    return terms


def exclusion_reason(term: str) -> str:
    cleaned = term.strip()
    letters = [character for character in cleaned if character.isalpha()]
    alpha = "".join(letters)

    if not cleaned:
        return "blank"
    if re.match(r"^\d", cleaned):
        return "formula-or-leading-number"
    if "," in cleaned or "[" in cleaned or "]" in cleaned:
        return "formula-or-bracket-notation"
    if "." in cleaned:
        return "dotted-abbreviation"
    if re.fullmatch(r"[A-Za-z]*\d[A-Za-z0-9-]*", cleaned):
        return "alphanumeric-shorthand"
    if alpha and alpha.upper() == alpha and len(alpha) <= 8:
        return "all-caps-acronym"
    return ""


def normalized_entry(item: dict[str, Any], require_source_evidence: bool = True) -> dict[str, Any]:
    term = str(item.get("term") or "").strip()
    pronunciation = str(item.get("pronunciation") or "").strip()
    syllables = str(item.get("syllables") or "").strip()
    source = str(item.get("source") or "").strip()
    notes = str(item.get("notes") or "").strip()
    if not term or not pronunciation or not syllables:
        raise ValueError(f"Entry is missing term, pronunciation, or syllables: {term!r}")
    if require_source_evidence and not source and not notes:
        raise ValueError(f"Entry must include source or notes evidence: {term}")
    if not any(character.isupper() for character in pronunciation):
        raise ValueError(f"Entry lacks a stress marker: {term}")

    entry = dict(item)
    entry["term"] = term
    entry["pronunciation"] = pronunciation
    entry["syllables"] = syllables
    if not str(entry.get("speechText") or "").strip():
        speech_text = pronunciation_to_speech_text(pronunciation)
        if not speech_text:
            raise ValueError(f"Entry cannot derive speechText: {term}")
        entry["speechText"] = speech_text
    return ordered_item(entry)


def source_verified_entry(item: dict[str, Any]) -> dict[str, Any]:
    return normalized_entry(item, require_source_evidence=True)


def generated_entry(term: str, phones: list[str]) -> dict[str, Any]:
    pronunciation = arpabet_to_pronounceit(phones)
    if not pronunciation:
        raise ValueError(f"Unable to generate pronunciation for: {term}")
    return normalized_entry(
        {
            "term": term,
            "pronunciation": pronunciation,
            "syllables": pronunciation.lower(),
            "speechText": pronunciation_to_speech_text(pronunciation),
            "source": GENERATED_SOURCE,
            "notes": GENERATED_NOTES,
        },
        require_source_evidence=False,
    )


def fallback_generated_entry(term: str) -> dict[str, Any]:
    speech_text = pronunciation_to_speech_text(term)
    pronunciation = speech_text.upper() if speech_text else term.upper()
    return normalized_entry(
        {
            "term": term,
            "pronunciation": pronunciation,
            "syllables": speech_text or term.lower(),
            "speechText": speech_text or term.lower(),
            "source": GENERATED_SOURCE,
            "notes": FALLBACK_GENERATED_NOTES,
        },
        require_source_evidence=False,
    )


def arpabet_to_pronounceit(phones: list[str]) -> str:
    syllables: list[dict[str, Any]] = []
    pending_consonants: list[str] = []

    for raw_phone in phones:
        phone = raw_phone.strip()
        if not phone or not phone.isascii():
            continue
        match = PHONE_RE.match(phone)
        if not match:
            continue
        base, stress = match.groups()
        readable = ARPABET_TO_READABLE.get(base)
        if readable is None:
            continue
        if base in VOWELS:
            if pending_consonants and syllables and stress == "0" and syllables[-1]["stress"] in {"1", "2"}:
                syllables[-1]["parts"].extend(pending_consonants)
                pending_consonants = []
            syllables.append({"parts": pending_consonants + [readable], "stress": stress})
            pending_consonants = []
            continue
        pending_consonants.append(readable)

    if pending_consonants:
        if syllables:
            syllables[-1]["parts"].extend(pending_consonants)
        else:
            syllables.append({"parts": pending_consonants, "stress": ""})

    rendered: list[str] = []
    for syllable in syllables:
        text = "".join(syllable["parts"])
        if syllable["stress"] in {"1", "2"}:
            text = text.upper()
        rendered.append(text)
    return "-".join(part for part in rendered if part)


class G2pGenerator:
    def __init__(self) -> None:
        try:
            from g2p_en import G2p
        except ImportError as exc:
            raise SystemExit(
                "g2p-en is required for --allow-generated. "
                "Install generation dependencies with: "
                "python3 -m pip install -r requirements-generation.txt"
            ) from exc
        self._g2p = G2p()

    def phones_for(self, term: str) -> list[str]:
        return [
            token
            for token in self._g2p(term)
            if isinstance(token, str) and PHONE_RE.match(token.strip())
        ]


def load_verified_source(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("terms", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("Verified source must be a JSON list or an object with a terms list.")

    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = source_verified_entry(item)
        by_key[normalize_key(entry["term"])] = entry
        for alias in entry.get("aliases", []):
            if isinstance(alias, str) and alias.strip():
                by_key[normalize_key(alias)] = entry
    return by_key


def existing_dictionary_keys(data_file: Path) -> set[str]:
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for item in raw.get("terms", []):
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if term:
            keys.add(normalize_key(term))
        for alias in item.get("aliases", []):
            if isinstance(alias, str) and alias.strip():
                keys.add(normalize_key(alias))
    return keys


def build_outputs(
    wordlist_file: Path,
    data_file: Path,
    verified_source_file: Path | None = None,
    allow_generated: bool = False,
    generator: Any | None = None,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], list[tuple[str, str]]]:
    verified = load_verified_source(verified_source_file)
    existing_keys = existing_dictionary_keys(data_file)
    dictionary = PronunciationDictionary.bundled(data_file=data_file)
    active_generator = generator
    if allow_generated and active_generator is None:
        active_generator = G2pGenerator()

    accepted: list[dict[str, Any]] = []
    accepted_keys: set[str] = set()
    excluded: list[tuple[str, str]] = []
    needs_review: list[tuple[str, str]] = []

    for term in load_wordlist(wordlist_file):
        reason = exclusion_reason(term)
        if reason:
            excluded.append((term, reason))
            continue

        key = normalize_key(term)
        if key in existing_keys or dictionary.lookup(term).get("found"):
            continue

        entry = verified.get(key)
        if entry is None:
            if not allow_generated:
                needs_review.append((term, "source-verification-needed"))
                continue
            try:
                entry = generated_entry(term, active_generator.phones_for(term))
            except ValueError:
                entry = fallback_generated_entry(term)

        entry_key = normalize_key(entry["term"])
        if entry_key not in accepted_keys and entry_key not in existing_keys:
            accepted.append(entry)
            accepted_keys.add(entry_key)

    return accepted, excluded, needs_review


def write_outputs(
    accepted: list[dict[str, Any]],
    excluded: list[tuple[str, str]],
    needs_review: list[tuple[str, str]],
    accepted_file: Path = DEFAULT_ACCEPTED_FILE,
    excluded_file: Path = DEFAULT_EXCLUDED_FILE,
    needs_review_file: Path = DEFAULT_NEEDS_REVIEW_FILE,
) -> None:
    accepted_file.write_text(
        json.dumps({"version": 1, "terms": accepted}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_csv(excluded_file, ("term", "reason"), excluded)
    write_csv(needs_review_file, ("term", "reason"), needs_review)


def write_csv(path: Path, header: tuple[str, str], rows: list[tuple[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def merge_generated_entries(
    data_file: Path,
    accepted_entries: list[dict[str, Any]],
) -> dict[str, int]:
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    terms = raw.get("terms", [])
    if not isinstance(terms, list):
        terms = []

    existing = existing_dictionary_keys(data_file)
    added = 0
    skipped = 0
    pruned = 0
    kept_terms = []
    for item in terms:
        if not isinstance(item, dict):
            continue
        if item.get("source") == GENERATED_SOURCE and exclusion_reason(str(item.get("term") or "")):
            pruned += 1
            continue
        kept_terms.append(item)
    terms = kept_terms
    if pruned:
        existing = existing_dictionary_keys_from_items(terms)

    for item in accepted_entries:
        entry = normalized_entry(item, require_source_evidence=True)
        key = normalize_key(entry["term"])
        if key in existing:
            skipped += 1
            continue
        terms.append(entry)
        existing.add(key)
        for alias in entry.get("aliases", []):
            if isinstance(alias, str):
                existing.add(normalize_key(alias))
        added += 1

    raw["terms"] = [ordered_item(item) for item in terms if isinstance(item, dict)]
    data_file.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"added": added, "skipped": skipped, "pruned": pruned, "totalTerms": len(raw["terms"])}


def existing_dictionary_keys_from_items(items: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in items:
        term = str(item.get("term") or "").strip()
        if term:
            keys.add(normalize_key(term))
        for alias in item.get("aliases", []):
            if isinstance(alias, str) and alias.strip():
                keys.add(normalize_key(alias))
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build PronounceIt entries from a large word list."
    )
    parser.add_argument("--wordlist-file", type=Path, default=DEFAULT_WORDLIST_FILE)
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--verified-source-file", type=Path)
    parser.add_argument("--allow-generated", action="store_true")
    parser.add_argument("--generator", choices=["g2p-en"], default="g2p-en")
    parser.add_argument("--accepted-file", type=Path, default=DEFAULT_ACCEPTED_FILE)
    parser.add_argument("--excluded-file", type=Path, default=DEFAULT_EXCLUDED_FILE)
    parser.add_argument("--needs-review-file", type=Path, default=DEFAULT_NEEDS_REVIEW_FILE)
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()

    accepted, excluded, needs_review = build_outputs(
        args.wordlist_file,
        args.data_file,
        args.verified_source_file,
        args.allow_generated,
    )
    write_outputs(
        accepted,
        excluded,
        needs_review,
        args.accepted_file,
        args.excluded_file,
        args.needs_review_file,
    )

    result: dict[str, Any] = {
        "accepted": len(accepted),
        "excluded": len(excluded),
        "needsReview": len(needs_review),
    }
    if args.merge:
        result["merge"] = merge_generated_entries(args.data_file, accepted)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
