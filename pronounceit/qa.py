from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dictionary import DATA_FILE, PronunciationDictionary


CHECKLIST_FILE = Path(__file__).resolve().parent.parent / "data" / "high_yield_checklist.json"
SOURCE_LEXICON_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "medical_pronunciation_lexicon_for_codex.txt"
)


@dataclass(frozen=True)
class PronunciationAudit:
    dictionary_terms: int
    checklist_terms: int
    missing_terms: list[str]
    missing_pronunciation: list[str]
    missing_syllables: list[str]
    missing_speech_text: list[str]
    missing_audio_files: list[str]
    unsafe_speech_text: list[str]
    missing_stress_marker: list[str]
    source_lexicon_terms: int
    missing_source_lexicon_terms: list[str]
    source_lexicon_pronunciation_mismatches: list[str]

    @property
    def passed(self) -> bool:
        return not any(
            [
                self.missing_terms,
                self.missing_pronunciation,
                self.missing_syllables,
                self.missing_speech_text,
                self.missing_audio_files,
                self.unsafe_speech_text,
                self.missing_stress_marker,
                self.missing_source_lexicon_terms,
                self.source_lexicon_pronunciation_mismatches,
            ]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "dictionaryTerms": self.dictionary_terms,
            "checklistTerms": self.checklist_terms,
            "missingTerms": self.missing_terms,
            "missingPronunciation": self.missing_pronunciation,
            "missingSyllables": self.missing_syllables,
            "missingSpeechText": self.missing_speech_text,
            "missingAudioFiles": self.missing_audio_files,
            "unsafeSpeechText": self.unsafe_speech_text,
            "missingStressMarker": self.missing_stress_marker,
            "sourceLexiconTerms": self.source_lexicon_terms,
            "missingSourceLexiconTerms": self.missing_source_lexicon_terms,
            "sourceLexiconPronunciationMismatches": self.source_lexicon_pronunciation_mismatches,
        }


def load_checklist(path: Path = CHECKLIST_FILE) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    terms: list[str] = []
    for category in raw.get("categories", []):
        for term in category.get("terms", []):
            if isinstance(term, str) and term.strip():
                terms.append(term.strip())
    return terms


def load_source_lexicon(path: Path = SOURCE_LEXICON_FILE) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        if "|" not in line or line.lower().startswith("term |"):
            continue
        term, pronunciation = [part.strip() for part in line.split("|", 1)]
        if term and pronunciation:
            entries.append((term, pronunciation))
    return entries


def audit_pronunciations(
    data_file: Path = DATA_FILE,
    checklist_file: Path = CHECKLIST_FILE,
    source_lexicon_file: Path = SOURCE_LEXICON_FILE,
    audio_root: Path | None = None,
) -> PronunciationAudit:
    dictionary = PronunciationDictionary.bundled(data_file=data_file)
    root = audio_root or Path(__file__).resolve().parent.parent
    checklist = load_checklist(checklist_file)
    source_lexicon = load_source_lexicon(source_lexicon_file)
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    entries = raw.get("terms", [])

    missing_terms = [term for term in checklist if not dictionary.lookup(term)["found"]]
    missing_source_lexicon_terms = [
        term for term, _pronunciation in source_lexicon if not dictionary.lookup(term)["found"]
    ]
    source_lexicon_pronunciation_mismatches: list[str] = []
    for term, pronunciation in source_lexicon:
        payload = dictionary.lookup(term)
        if payload["found"] and payload.get("pronunciation") != pronunciation:
            source_lexicon_pronunciation_mismatches.append(term)
    missing_pronunciation: list[str] = []
    missing_syllables: list[str] = []
    missing_speech_text: list[str] = []
    missing_audio_files: list[str] = []
    unsafe_speech_text: list[str] = []
    missing_stress_marker: list[str] = []

    for item in entries:
        term = item.get("term", "")
        payload = dictionary.lookup(term)
        if not payload.get("pronunciation"):
            missing_pronunciation.append(term)
        if not payload.get("syllables"):
            missing_syllables.append(term)
        if not payload.get("speechText"):
            missing_speech_text.append(term)
        audio_file = str(payload.get("audioFile", ""))
        audio_path = root / audio_file
        if not audio_file or not audio_path.exists() or audio_path.stat().st_size == 0:
            missing_audio_files.append(term)
        speech_text = str(payload.get("speechText", ""))
        if (
            "-" in speech_text
            or any(character.isupper() for character in speech_text)
            or (
                " or " in str(payload.get("pronunciation", "")).lower()
                and " or " in f" {speech_text} "
            )
        ):
            unsafe_speech_text.append(term)
        if not any(character.isupper() for character in str(payload.get("pronunciation", ""))):
            missing_stress_marker.append(term)

    return PronunciationAudit(
        dictionary_terms=dictionary.count(),
        checklist_terms=len(checklist),
        missing_terms=missing_terms,
        missing_pronunciation=missing_pronunciation,
        missing_syllables=missing_syllables,
        missing_speech_text=missing_speech_text,
        missing_audio_files=missing_audio_files,
        unsafe_speech_text=unsafe_speech_text,
        missing_stress_marker=missing_stress_marker,
        source_lexicon_terms=len(source_lexicon),
        missing_source_lexicon_terms=missing_source_lexicon_terms,
        source_lexicon_pronunciation_mismatches=source_lexicon_pronunciation_mismatches,
    )
