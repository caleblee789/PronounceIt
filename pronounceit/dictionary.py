from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "medical_pronunciations.json"
TERM_RE = re.compile(r"[^\s.,;!?{}\[\]<>\"`][^.,;!?{}\[\]<>\"`]{0,79}")


@dataclass(frozen=True)
class PronunciationEntry:
    term: str
    pronunciation: str
    syllables: str
    speech_text: str = ""
    audio_file: str = ""
    source: str = "bundled-medical"
    notes: str = ""

    def as_payload(self, requested_text: str) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("speech_text", None)
        payload.pop("audio_file", None)
        payload["requestedText"] = requested_text
        payload["speechText"] = self.speech_text or pronunciation_to_speech_text(self.pronunciation)
        payload["audioFile"] = self.audio_file or default_audio_file(self.term)
        payload["found"] = True
        return payload


def normalize_term(value: str) -> str:
    cleaned = " ".join(value.replace("\u00a0", " ").split())
    cleaned = strip_trailing_parenthetical(cleaned)
    cleaned = cleaned.strip(".,;:!?()[]{}<>\"`")
    cleaned = re.sub(r"[\u2010-\u2015-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.casefold()


def display_term(value: str) -> str:
    cleaned = " ".join(value.replace("\u00a0", " ").split())
    cleaned = strip_trailing_parenthetical(cleaned)
    return cleaned.strip(".,;:!?()[]{}<>\"`")


def strip_trailing_parenthetical(value: str) -> str:
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*$", "", value).strip()


def is_plausible_selection(value: str) -> bool:
    text = display_term(value)
    word_count = len([part for part in re.split(r"\s+", text) if part])
    return bool(text) and word_count <= 4 and bool(TERM_RE.fullmatch(text))


class PronunciationDictionary:
    def __init__(self, entries: dict[str, PronunciationEntry]) -> None:
        self._entries = entries

    @classmethod
    def bundled(
        cls,
        data_file: Path = DATA_FILE,
        user_file: Path | None = None,
    ) -> "PronunciationDictionary":
        entries: dict[str, PronunciationEntry] = {}
        cls._merge_entries(entries, _read_terms_file(data_file), "bundled-medical")
        if user_file and user_file.exists():
            cls._merge_entries(entries, _read_terms_file(user_file), "user-override")
        return cls(entries)

    @staticmethod
    def _merge_entries(
        entries: dict[str, PronunciationEntry],
        items: list[dict[str, Any]],
        default_source: str,
    ) -> None:
        for item in items:
            entry = PronunciationEntry(
                term=item["term"],
                pronunciation=item["pronunciation"],
                syllables=item["syllables"],
                speech_text=item.get("speechText") or item.get("speech_text", ""),
                audio_file=item.get("audioFile") or item.get("audio_file", ""),
                source=item.get("source", default_source),
                notes=item.get("notes", ""),
            )
            entries[normalize_term(entry.term)] = entry
            for alias in item.get("aliases", []):
                entries[normalize_term(alias)] = entry

    def lookup(self, selected_text: str) -> dict[str, Any]:
        clean = display_term(selected_text)
        if not is_plausible_selection(clean):
            return unknown_payload(clean, reason="unsupported-selection")

        entry = self._find_entry(clean)
        if entry:
            return entry.as_payload(clean)
        return unknown_payload(clean)

    def contains(self, term: str) -> bool:
        return self._find_entry(term) is not None

    def count(self) -> int:
        return len({entry.term.casefold() for entry in self._entries.values()})

    def _find_entry(self, term: str) -> PronunciationEntry | None:
        for variant in lookup_variants(term):
            entry = self._entries.get(variant)
            if entry:
                return entry
        return None


def lookup_variants(value: str) -> list[str]:
    normalized = normalize_term(value)
    variants = [normalized]

    if normalized.endswith("'s"):
        variants.append(normalized[:-2])
    elif normalized.endswith("s'"):
        variants.append(normalized[:-1])
    elif normalized.endswith("ies") and len(normalized) > 4:
        variants.append(normalized[:-3] + "y")
    elif normalized.endswith("es") and len(normalized) > 3:
        variants.append(normalized[:-2])
    elif normalized.endswith("s") and len(normalized) > 3:
        variants.append(normalized[:-1])

    deduped: list[str] = []
    for variant in variants:
        if variant and variant not in deduped:
            deduped.append(variant)
    return deduped


def unknown_payload(term: str, reason: str = "not-in-dictionary") -> dict[str, Any]:
    return {
        "requestedText": term,
        "term": term,
        "pronunciation": "",
        "syllables": "",
        "speechText": term,
        "audioFile": "",
        "source": "tts-only",
        "notes": "",
        "found": False,
        "reason": reason,
    }


def pronunciation_to_speech_text(value: str) -> str:
    text = value.lower()
    text = re.sub(r"[-/]", " ", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def audio_slug(value: str) -> str:
    slug = normalize_term(value)
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def default_audio_file(term: str) -> str:
    slug = audio_slug(term)
    return f"audio/{slug}.aiff" if slug else ""


def _read_terms_file(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        terms = raw.get("terms", [])
    else:
        terms = raw
    if not isinstance(terms, list):
        return []
    return [item for item in terms if isinstance(item, dict)]
