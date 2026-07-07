from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "medical_pronunciations.json"
HIGH_YIELD_FILE = Path(__file__).resolve().parent.parent / "data" / "high_yield_checklist.json"
TERM_RE = re.compile(r"[^\s.,;!?{}\[\]<>\"`][^.,;!?{}\[\]<>\"`]{0,79}")
CLOZE_RE = re.compile(r"\{\{c\d+::([^{}]*?)(?:::[^{}]*)?\}\}", re.IGNORECASE)
CONTEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\u2010-\u2015-]*")
CONTEXT_BOUNDARY_RE = re.compile(r"[\n\r.,;:!?{}\[\]<>\"`]")


@dataclass(frozen=True)
class PronunciationEntry:
    term: str
    pronunciation: str
    syllables: str
    speech_text: str = ""
    audio_file: str = ""
    source: str = "bundled-medical"
    notes: str = ""
    quality_tier: str = "curated"
    sapi_phonemes: str = ""
    sapi_segments: tuple[dict[str, str], ...] = ()

    def as_payload(self, requested_text: str) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("speech_text", None)
        payload.pop("audio_file", None)
        payload.pop("sapi_segments", None)
        payload["requestedText"] = requested_text
        payload["speechText"] = self.speech_text or pronunciation_to_speech_text(self.pronunciation)
        payload["synthesisText"] = (
            payload["speechText"] if self.source == "user-override" and self.speech_text else self.term
        )
        payload["audioFile"] = self.audio_file or default_audio_file(self.term)
        payload["qualityTier"] = self.quality_tier
        payload["synthesisStrategy"] = (
            "manual-sapi" if self.sapi_phonemes or self.sapi_segments else "azure-native"
        )
        payload["audioReviewStatus"] = "passed" if payload["audioFile"] else "unreviewed"
        if self.sapi_phonemes:
            payload["sapiPhonemes"] = self.sapi_phonemes
        if self.sapi_segments:
            payload["sapiSegments"] = [dict(segment) for segment in self.sapi_segments]
        payload["found"] = True
        return payload


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


def _parse_sapi_segments(value: Any) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        return ()
    segments: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            return ()
        text = str(item.get("text") or "").strip()
        sapi = str(item.get("sapi") or "").strip()
        if not text or not sapi:
            return ()
        segments.append({"text": text, "sapi": sapi})
    return tuple(segments)


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
        verified_terms = _load_high_yield_terms()
        for item in bundled_items:
            if not isinstance(item, dict):
                continue
            aliases = item.get("aliases", [])
            if isinstance(aliases, list) and any(
                isinstance(alias, str) and normalize_term(alias) in verified_terms
                for alias in aliases
            ):
                verified_terms.add(normalize_term(str(item.get("term") or "")))
        cls._merge_entries(
            entries,
            bundled_items,
            "bundled-medical",
            issues,
            strict=True,
            verified_terms=verified_terms,
        )
        if user_file and user_file.exists():
            try:
                user_items = _read_terms_file(user_file)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                issues.append(f"{user_file}: could not load custom pronunciations: {exc}")
            else:
                cls._merge_entries(
                    entries,
                    user_items,
                    "user-override",
                    issues,
                    strict=False,
                )
        return cls(entries, issues)

    @staticmethod
    def _merge_entries(
        entries: dict[str, PronunciationEntry],
        items: list[Any],
        default_source: str,
        issues: list[str] | None = None,
        strict: bool = True,
        verified_terms: set[str] | None = None,
    ) -> None:
        load_issues = issues if issues is not None else []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                message = f"entry {index + 1} is not a JSON object"
                if strict:
                    raise ValueError(message)
                load_issues.append(message)
                continue
            missing = [
                key
                for key in ("term", "pronunciation", "syllables")
                if not isinstance(item.get(key), str) or not item.get(key, "").strip()
            ]
            if missing:
                message = f"entry {index + 1} is missing valid fields: {', '.join(missing)}"
                if strict:
                    raise ValueError(message)
                load_issues.append(message)
                continue
            source = item.get("source", default_source)
            normalized_term = normalize_term(item["term"])
            quality_tier = str(item.get("qualityTier") or "").strip().casefold()
            if quality_tier not in {"verified", "curated", "generated", "fallback"}:
                if source == "user-override" or normalized_term in (verified_terms or set()):
                    quality_tier = "verified"
                elif source == "generated-g2p-en":
                    quality_tier = (
                        "fallback"
                        if "fallback from raw spelling" in str(item.get("notes") or "").casefold()
                        else "generated"
                    )
                else:
                    quality_tier = "curated"
            entry = PronunciationEntry(
                term=item["term"],
                pronunciation=item["pronunciation"],
                syllables=item["syllables"],
                speech_text=item.get("speechText") or item.get("speech_text", ""),
                audio_file=item.get("audioFile") or item.get("audio_file", ""),
                source=source,
                notes=item.get("notes", ""),
                quality_tier=quality_tier,
                sapi_phonemes=item.get("sapiPhonemes") or item.get("sapi_phonemes", ""),
                sapi_segments=_parse_sapi_segments(
                    item.get("sapiSegments") or item.get("sapi_segments", [])
                ),
            )
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
        "source": "tts-only",
        "qualityTier": "fallback",
        "synthesisStrategy": "azure-native",
        "audioReviewStatus": "unreviewed",
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
    if not slug:
        return ""
    mp3_path = Path(__file__).resolve().parent.parent / "audio" / f"{slug}.mp3"
    if mp3_path.is_file():
        return f"audio/{slug}.mp3"
    aiff_path = Path(__file__).resolve().parent.parent / "audio" / f"{slug}.aiff"
    return f"audio/{slug}.aiff" if aiff_path.is_file() else ""


def _read_terms_file(path: Path) -> list[Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        terms = raw.get("terms", [])
    else:
        terms = raw
    if not isinstance(terms, list):
        raise ValueError("expected 'terms' to be a JSON list")
    return terms


def _load_high_yield_terms(path: Path = HIGH_YIELD_FILE) -> set[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    verified: set[str] = set()
    for category in raw.get("categories", []):
        if not isinstance(category, dict):
            continue
        for term in category.get("terms", []):
            if isinstance(term, str):
                verified.update(lookup_variants(term))
    return verified
