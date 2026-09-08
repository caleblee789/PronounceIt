from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "audio_pronunciations.json"
TERM_RE = re.compile(r"[^\s.,;!?{}\[\]<>\"`][^.,;!?{}\[\]<>\"`]{0,79}")
CLOZE_RE = re.compile(r"\{\{c\d+::([^{}]*?)(?:::[^{}]*)?\}\}", re.IGNORECASE)
CONTEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\u2010-\u2015-]*")
CONTEXT_BOUNDARY_RE = re.compile(r"[\n\r.,;:!?{}\[\]<>\"`]")


@dataclass(frozen=True)
class PronunciationEntry:
    term: str
    pronunciation: str
    syllables: str = ""
    speech_text: str = ""
    audio_file: str = ""
    custom: bool = False
    notes: str = ""

    def as_payload(self, requested_text: str) -> dict[str, Any]:
        override = self.custom and bool(self.speech_text)
        return {
            "term": self.term,
            "requestedText": requested_text,
            "pronunciation": self.pronunciation,
            "syllables": self.syllables,
            "speechText": self.speech_text if override else self.term,
            "synthesisText": self.speech_text if override else self.term,
            "useTextOverride": override,
            "audioFile": self.audio_file,
            "custom": self.custom,
            "notes": self.notes,
            "found": True,
        }


def normalize_term(value: str) -> str:
    cleaned = " ".join(strip_cloze_markup(value).replace("\u00a0", " ").split())
    cleaned = strip_trailing_parenthetical(cleaned)
    cleaned = _strip_edge_punctuation(cleaned)
    cleaned = re.sub(r"[\u2010-\u2015-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.casefold()


def display_term(value: str) -> str:
    cleaned = " ".join(strip_cloze_markup(value).replace("\u00a0", " ").split())
    cleaned = strip_trailing_parenthetical(cleaned)
    return _strip_edge_punctuation(cleaned)


def _strip_edge_punctuation(value: str) -> str:
    if re.search(r"\(o\)$", value, flags=re.IGNORECASE):
        return value.strip(".,;:!?[]{}<>\"`")
    return value.strip(".,;:!?()[]{}<>\"`")


def strip_cloze_markup(value: str) -> str:
    return CLOZE_RE.sub(lambda match: match.group(1), str(value or ""))


def strip_trailing_parenthetical(value: str) -> str:
    match = re.search(r"\s*[\(\[]([^\)\]]*)[\)\]]\s*$", value)
    if not match or match.group(1).strip().casefold() == "o":
        return value.strip()
    return value[: match.start()].strip()


def is_plausible_selection(value: str) -> bool:
    text = display_term(value)
    word_count = len([part for part in re.split(r"\s+", text) if part])
    return bool(text) and word_count <= 4 and bool(TERM_RE.fullmatch(text))


class PronunciationDictionary:
    def __init__(
        self,
        entries: dict[str, PronunciationEntry],
        load_issues: list[str] | None = None,
    ) -> None:
        self._entries = entries
        self.load_issues = list(load_issues or [])

    @classmethod
    def bundled(
        cls,
        data_file: Path = DATA_FILE,
        user_file: Path | None = None,
    ) -> "PronunciationDictionary":
        entries: dict[str, PronunciationEntry] = {}
        issues: list[str] = []
        bundled_items = _read_terms_file(data_file)
        written_file = data_file.with_name("written_pronunciations.json")
        written = None
        if written_file.exists() or data_file.resolve() == DATA_FILE.resolve():
            from .written_guides import load_written_guides
            try:
                written = load_written_guides(written_file, bundled_items)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                issues.append(f"Written pronunciations unavailable: {exc}")
                # Audio and term lookup still work when display data is damaged.
                written = {}
        cls._merge_entries(entries, bundled_items, False, issues, written_guides=written)
        if user_file and user_file.exists():
            try:
                user_items = _read_terms_file(user_file)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                issues.append(f"{user_file}: could not load custom pronunciations: {exc}")
            else:
                cls._merge_entries(
                    entries,
                    user_items,
                    True,
                    issues,
                    strict=False,
                )
        return cls(entries, issues)

    @staticmethod
    def _merge_entries(
        entries: dict[str, PronunciationEntry],
        items: list[Any],
        custom: bool,
        issues: list[str] | None = None,
        strict: bool = True,
        written_guides: dict[str, dict] | None = None,
    ) -> None:
        load_issues = issues if issues is not None else []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                message = f"entry {index + 1} is not a JSON object"
                if strict:
                    raise ValueError(message)
                load_issues.append(message)
                continue
            required = ("term", "pronunciation") if written_guides is None else ("term",)
            missing = [
                key
                for key in required
                if not isinstance(item.get(key), str) or not item.get(key, "").strip()
            ]
            if missing:
                message = f"entry {index + 1} is missing valid fields: {', '.join(missing)}"
                if strict:
                    raise ValueError(message)
                load_issues.append(message)
                continue
            entry = PronunciationEntry(
                term=item["term"],
                pronunciation=(written_guides.get(item["term"], {}).get("pronunciation", "")
                               if written_guides is not None else item["pronunciation"]),
                syllables=str(item.get("syllables") or "") if custom else "",
                speech_text=str(item.get("speechText") or item.get("speech_text") or "") if custom else "",
                audio_file=str(item.get("audioFile") or item.get("audio_file") or "") if custom else "",
                custom=custom,
                notes=str(item.get("notes") or "") if custom else "",
            )
            previous = entries.get(normalize_term(entry.term))
            if custom and previous and normalize_term(previous.term) == normalize_term(entry.term):
                for alias, value in list(entries.items()):
                    if value is previous:
                        entries[alias] = entry
            entries[normalize_term(entry.term)] = entry
            aliases = item.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and normalize_term(alias):
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

    def best_context_match(
        self,
        context_text: str,
        start: int,
        end: int,
        max_words: int = 4,
    ) -> str:
        text = strip_cloze_markup(str(context_text or "")).replace("\u00a0", " ")
        if not text:
            return ""

        selected_start = max(0, min(int(start or 0), len(text)))
        selected_end = max(selected_start, min(int(end or selected_start), len(text)))
        tokens = list(CONTEXT_TOKEN_RE.finditer(text))
        if not tokens:
            return ""

        selected_indexes = [
            index
            for index, token in enumerate(tokens)
            if token.start() < selected_end and token.end() > selected_start
        ]
        if not selected_indexes:
            nearest_index = min(
                range(len(tokens)),
                key=lambda index: _span_distance(
                    tokens[index].start(),
                    tokens[index].end(),
                    selected_start,
                    selected_end,
                ),
            )
            selected_indexes = [nearest_index]

        first_selected = min(selected_indexes)
        last_selected = max(selected_indexes)
        best: tuple[int, int, int, str] | None = None

        for first in range(max(0, last_selected - max_words + 1), first_selected + 1):
            for last in range(last_selected, min(len(tokens), first + max_words)):
                word_count = last - first + 1
                if first > first_selected or last < last_selected:
                    continue
                if word_count > max_words:
                    continue
                if _tokens_cross_context_boundary(text, tokens, first, last):
                    continue
                candidate = display_term(text[tokens[first].start() : tokens[last].end()])
                if not candidate or not self.contains(candidate):
                    continue
                distance = _span_distance(
                    tokens[first].start(),
                    tokens[last].end(),
                    selected_start,
                    selected_end,
                )
                score = (-word_count, distance, tokens[first].start(), candidate)
                if best is None or score < best:
                    best = score

        return best[3] if best else ""

    def context_fallback_term(
        self,
        context_text: str,
        start: int,
        end: int,
        max_words: int = 4,
    ) -> str:
        text = strip_cloze_markup(str(context_text or "")).replace("\u00a0", " ")
        if not text:
            return ""

        selected_start = max(0, min(int(start or 0), len(text)))
        selected_end = max(selected_start, min(int(end or selected_start), len(text)))
        tokens = list(CONTEXT_TOKEN_RE.finditer(text))
        if not tokens:
            return ""

        selected_indexes = [
            index
            for index, token in enumerate(tokens)
            if token.start() < selected_end and token.end() > selected_start
        ]
        if not selected_indexes:
            nearest_index = min(
                range(len(tokens)),
                key=lambda index: _span_distance(
                    tokens[index].start(),
                    tokens[index].end(),
                    selected_start,
                    selected_end,
                ),
            )
            selected_indexes = [nearest_index]

        first = min(selected_indexes)
        last = max(selected_indexes)
        if last - first + 1 > max_words:
            return ""
        if _tokens_cross_context_boundary(text, tokens, first, last):
            return ""
        return display_term(text[tokens[first].start() : tokens[last].end()])

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

    variants.extend(_final_word_variants(normalized))

    if " " in normalized:
        prefix, final_word = normalized.rsplit(" ", 1)
        for final_variant in _final_word_variants(final_word):
            variants.append(f"{prefix} {final_variant}")

    deduped: list[str] = []
    for variant in variants:
        if variant and variant not in deduped:
            deduped.append(variant)
    return deduped


def _final_word_variants(word: str) -> list[str]:
    variants: list[str] = []
    if word.endswith("'s"):
        variants.append(word[:-2])
    elif word.endswith("s'"):
        variants.append(word[:-1])
    elif word.endswith("ies") and len(word) > 4:
        variants.append(word[:-3] + "y")
    elif word.endswith("es") and len(word) > 3:
        variants.append(word[:-2])
        variants.append(word[:-1])
    elif word.endswith("s") and len(word) > 3:
        variants.append(word[:-1])
    return variants


def _span_distance(start: int, end: int, selected_start: int, selected_end: int) -> int:
    if start < selected_end and end > selected_start:
        return 0
    if end <= selected_start:
        return selected_start - end
    return start - selected_end


def _tokens_cross_context_boundary(text: str, tokens: list[re.Match[str]], first: int, last: int) -> bool:
    for index in range(first, last):
        between = text[tokens[index].end() : tokens[index + 1].start()]
        if CONTEXT_BOUNDARY_RE.search(between):
            return True
    return False


def unknown_payload(term: str, reason: str = "not-in-dictionary") -> dict[str, Any]:
    return {
        "requestedText": term,
        "term": term,
        "pronunciation": "",
        "syllables": "",
        "speechText": term,
        "synthesisText": term,
        "audioFile": "",
        "custom": False,
        "useTextOverride": False,
        "notes": "",
        "found": False,
        "reason": reason,
    }


def _read_terms_file(path: Path) -> list[Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        terms = raw.get("terms", [])
    else:
        terms = raw
    if not isinstance(terms, list):
        raise ValueError("expected 'terms' to be a JSON list")
    return terms
