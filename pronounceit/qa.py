"""Integrity checks for the complete audio and written pronunciation library."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audio_pack import audio_asset_id, file_sha256
from .dictionary import BUNDLED_PRONUNCIATION_EXCLUSIONS, DATA_FILE, normalize_term
from .written_guides import (
    ANKING_WRITTEN_FILE, canonical_terms_sha256, load_written_guides, load_written_supplement,
)


@dataclass(frozen=True)
class PronunciationAudit:
    dictionary_terms: int
    audio_terms: int
    written_terms: int
    errors: list[str]

    @property
    def passed(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "terms": self.dictionary_terms,
                "audioPronunciations": self.audio_terms,
                "writtenPronunciations": self.written_terms, "errors": self.errors}


def audit_pronunciations(data_file: Path = DATA_FILE) -> PronunciationAudit:
    audio_terms = written_terms = count = 0
    errors: list[str] = []
    try:
        raw = json.loads(data_file.read_text(encoding="utf-8"))
        items = raw["terms"]
        if raw.get("schemaVersion") != 1 or not isinstance(items, list) or not items:
            raise ValueError("invalid audio-pronunciation inventory")
        identifiers = set()
        active_terms = set()
        for item in items:
            if (not isinstance(item.get("term"), str) or not item["term"].strip()
                    or item.get("assetId") != audio_asset_id(item["term"])
                    or item["assetId"] in identifiers):
                raise ValueError("invalid or duplicate audio term")
            aliases = item.get("aliases", [])
            if not isinstance(aliases, list) or any(not isinstance(a, str) or not a.strip() for a in aliases):
                raise ValueError("invalid pronunciation alias")
            identifiers.add(item["assetId"])
            if normalize_term(item["term"]) not in BUNDLED_PRONUNCIATION_EXCLUSIONS:
                active_terms.add(item["term"])
        if raw.get("canonicalTermsSha256") != canonical_terms_sha256(items):
            raise ValueError("audio term or alias inventory changed")
        guides = load_written_guides(data_file.with_name("written_pronunciations.json"), items)
        if any(not record["pronunciation"].strip() for record in guides.values()):
            errors.append("The written-pronunciation inventory is incomplete.")
        count = audio_terms = len(active_terms)
        written_terms = sum(bool(guides[term]["pronunciation"].strip()) for term in active_terms)
        supplement = data_file.with_name(ANKING_WRITTEN_FILE)
        if supplement.exists():
            existing = {
                normalize_term(term)
                for item in items
                for term in (item["term"], *item.get("aliases", []))
            }
            additions = load_written_supplement(
                json.loads(supplement.read_text(encoding="utf-8")), existing,
            )
            active_additions = sum(addition["term"] not in BUNDLED_PRONUNCIATION_EXCLUSIONS for addition in additions)
            count += active_additions
            written_terms += active_additions
        release = json.loads(data_file.with_name("audio-pack-release.json").read_text(encoding="utf-8"))
        if (release.get("schemaVersion") != 3 or release.get("audioLibrarySha256") != file_sha256(data_file)
                or any(len(str(release.get(key, ""))) != 64 for key in (
                    "dictionarySha256", "packManifestSha256", "packManifestContentSha256"))):
            errors.append("The audio inventory does not match its library download.")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(str(exc))
    return PronunciationAudit(count, audio_terms, written_terms, errors)
