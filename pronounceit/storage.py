from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SaveResult:
    saved: bool
    duplicate: bool
    total: int


class SavedPronunciations:
    def __init__(self, addon_root: Path) -> None:
        self.user_dir = addon_root / "user_files"
        self.path = self.user_dir / "saved_pronunciations.json"

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def save_entry(self, payload: dict[str, Any]) -> SaveResult:
        self.user_dir.mkdir(parents=True, exist_ok=True)
        items = self.load()
        key = str(payload.get("term") or payload.get("requestedText") or "").casefold()
        if not key:
            return SaveResult(saved=False, duplicate=False, total=len(items))
        for item in items:
            item_key = str(item.get("term") or item.get("requestedText") or "").casefold()
            if item_key == key:
                return SaveResult(saved=False, duplicate=True, total=len(items))

        record = {
            "term": payload.get("term") or payload.get("requestedText"),
            "requestedText": payload.get("requestedText") or payload.get("term"),
            "pronunciation": payload.get("pronunciation", ""),
            "syllables": payload.get("syllables", ""),
            "speechText": payload.get("speechText", ""),
            "audioFile": payload.get("audioFile", ""),
            "source": payload.get("source", ""),
            "found": bool(payload.get("found")),
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        items.append(record)
        self.path.write_text(json.dumps(items, indent=2, sort_keys=True), encoding="utf-8")
        return SaveResult(saved=True, duplicate=False, total=len(items))

    def contains(self, payload: dict[str, Any]) -> bool:
        key = str(payload.get("term") or payload.get("requestedText") or "").casefold()
        if not key:
            return False
        for item in self.load():
            item_key = str(item.get("term") or item.get("requestedText") or "").casefold()
            if item_key == key:
                return True
        return False


class CustomPronunciations:
    def __init__(self, addon_root: Path) -> None:
        self.user_dir = addon_root / "user_files"
        self.path = self.user_dir / "custom_pronunciations.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"terms": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"terms": []}
        if isinstance(data, list):
            return {"terms": [item for item in data if isinstance(item, dict)]}
        if not isinstance(data, dict):
            return {"terms": []}
        terms = data.get("terms", [])
        if not isinstance(terms, list):
            terms = []
        return {"terms": [item for item in terms if isinstance(item, dict)]}

    def upsert_entry(
        self,
        term: str,
        pronunciation: str,
        syllables: str,
        speech_text: str = "",
        notes: str = "Added from PronounceIt.",
    ) -> dict[str, Any]:
        self.user_dir.mkdir(parents=True, exist_ok=True)
        data = self.load()
        terms = data["terms"]
        record = {
            "term": term,
            "pronunciation": pronunciation,
            "syllables": syllables,
            "notes": notes,
        }
        if speech_text:
            record["speechText"] = speech_text
        target = term.casefold()
        for index, item in enumerate(terms):
            if str(item.get("term", "")).casefold() == target:
                terms[index] = {**item, **record}
                if not speech_text:
                    terms[index].pop("speechText", None)
                break
        else:
            terms.append(record)

        data["terms"] = terms
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return record


def format_saved_entries(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No saved pronunciations yet."

    lines = ["Saved Pronunciations", ""]
    for index, item in enumerate(items, start=1):
        term = item.get("term") or item.get("requestedText") or "Unknown term"
        pronunciation = item.get("pronunciation") or "Pronunciation unavailable"
        syllables = item.get("syllables") or "Syllables unavailable"
        created = item.get("createdAt") or "Unknown date"
        lines.extend(
            [
                f"{index}. {term}",
                f"   Pronunciation: {pronunciation}",
                f"   Syllables: {syllables}",
                f"   Saved: {created}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()
