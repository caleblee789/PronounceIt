from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SaveResult:
    saved: bool
    duplicate: bool
    total: int


class StorageError(RuntimeError):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Could not use {path}: {reason}")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise StorageError(path, str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise StorageError(path, f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc


def _atomic_write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup)

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except (OSError, TypeError, ValueError) as exc:
        if "temp_path" in locals():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise StorageError(path, str(exc)) from exc


class SavedPronunciations:
    def __init__(self, addon_root: Path) -> None:
        self.user_dir = addon_root / "user_files"
        self.path = self.user_dir / "saved_pronunciations.json"

    def load(self) -> list[dict[str, Any]]:
        data = self._load_raw()
        return [item for item in data if isinstance(item, dict)]

    def _load_raw(self) -> list[Any]:
        data = _read_json(self.path, [])
        if not isinstance(data, list):
            raise StorageError(self.path, "expected a JSON list")
        return data

    def save_entry(self, payload: dict[str, Any]) -> SaveResult:
        raw_items = self._load_raw()
        items = [item for item in raw_items if isinstance(item, dict)]
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
            "custom": bool(payload.get("custom") or payload.get("source") == "user-override"),
            "found": bool(payload.get("found")),
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        for key in ("cardId", "noteId", "deckId", "deckName", "useTextOverride", "synthesisText"):
            if payload.get(key) not in (None, ""):
                record[key] = payload[key]
        raw_items.append(record)
        _atomic_write_json(self.path, raw_items)
        return SaveResult(saved=True, duplicate=False, total=len(items) + 1)

    def contains(self, payload: dict[str, Any]) -> bool:
        key = saved_entry_key(payload)
        if not key:
            return False
        for item in self.load():
            if saved_entry_key(item) == key:
                return True
        return False

    def remove_entry(self, key: str) -> bool:
        target = str(key or "").casefold()
        if not target:
            return False
        items = self._load_raw()
        next_items = [
            item
            for item in items
            if not isinstance(item, dict) or saved_entry_key(item) != target
        ]
        if len(next_items) == len(items):
            return False
        _atomic_write_json(self.path, next_items)
        return True


class CustomPronunciations:
    def __init__(self, addon_root: Path) -> None:
        self.user_dir = addon_root / "user_files"
        self.path = self.user_dir / "custom_pronunciations.json"

    def load(self) -> dict[str, Any]:
        data = self._load_raw()
        return {**data, "terms": [item for item in data["terms"] if isinstance(item, dict)]}

    def _load_raw(self) -> dict[str, Any]:
        data = _read_json(self.path, {"terms": []})
        if isinstance(data, list):
            return {"terms": data}
        if not isinstance(data, dict):
            raise StorageError(self.path, "expected a JSON object or legacy list")
        terms = data.get("terms", [])
        if not isinstance(terms, list):
            raise StorageError(self.path, "expected 'terms' to be a JSON list")
        return {**data, "terms": terms}

    def upsert_entry(
        self,
        term: str,
        pronunciation: str,
        syllables: str = "",
        speech_text: str = "",
        notes: str = "Added from PronounceIt.",
    ) -> dict[str, Any]:
        data = self._load_raw()
        terms = data["terms"]
        record = {
            "term": term,
            "pronunciation": pronunciation,
            "notes": notes,
        }
        if syllables:
            record["syllables"] = syllables
        if speech_text:
            record["speechText"] = speech_text
        target = term.casefold()
        for index, item in enumerate(terms):
            if not isinstance(item, dict):
                continue
            if str(item.get("term", "")).casefold() == target:
                terms[index] = {**item, **record}
                if not speech_text:
                    terms[index].pop("speechText", None)
                    terms[index].pop("speech_text", None)
                break
        else:
            terms.append(record)

        data["terms"] = terms
        _atomic_write_json(self.path, data)
        return record


def format_saved_entries(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No saved pronunciations yet."

    lines = ["Saved Pronunciations", ""]
    for index, item in enumerate(items, start=1):
        term = item.get("term") or item.get("requestedText") or "Unknown term"
        pronunciation = item.get("pronunciation") or "Pronunciation unavailable"
        created = item.get("createdAt") or "Unknown date"
        lines.extend(
            [
                f"{index}. {term}",
                f"   Pronunciation: {pronunciation}",
                f"   Saved: {created}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def saved_entry_key(item: dict[str, Any]) -> str:
    return str(item.get("term") or item.get("requestedText") or "").casefold()
