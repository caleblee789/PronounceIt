"""Written pronunciations, independent of audio and source review records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import AbstractSet

from .dictionary import normalize_term

ANKING_WRITTEN_FILE = "anking-written-pronunciations.json"


def canonical_terms_sha256(items: list[dict]) -> str:
    identities = [{"term": x["term"], "aliases": x.get("aliases", [])} for x in items]
    return hashlib.sha256(json.dumps(identities, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_written_guides(path: Path, items: list[dict]) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 3:
        raise ValueError("unsupported written-pronunciation schema")
    if raw.get("canonicalTermsSha256") != canonical_terms_sha256(items):
        raise ValueError("written pronunciations belong to different terms or aliases")
    records = raw.get("terms")
    if not isinstance(records, list) or len(records) != len(items):
        raise ValueError("incomplete written-pronunciation inventory")
    result = {}
    for record, item in zip(records, items):
        if not isinstance(record, dict) or record.get("term") != item["term"]:
            raise ValueError("written-pronunciation canonical order differs")
        if record["term"] in result:
            raise ValueError("duplicate written-pronunciation term")
        if not isinstance(record.get("pronunciation"), str):
            raise ValueError("invalid written pronunciation")
        result[record["term"]] = record
    return result


def load_written_supplement(raw: object, existing_keys: AbstractSet[str]) -> list[dict]:
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise ValueError("unsupported AnKing written-pronunciation schema")
    records = raw.get("terms")
    if not isinstance(records, list) or not records:
        raise ValueError("empty AnKing written-pronunciation supplement")
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"term", "pronunciation", "references"}:
            raise ValueError("invalid AnKing written-pronunciation record")
        term, pronunciation, references = (record[key] for key in ("term", "pronunciation", "references"))
        if not isinstance(term, str) or not term or normalize_term(term) != term:
            raise ValueError("invalid AnKing written-pronunciation term")
        if term in seen or term in existing_keys:
            raise ValueError(f"duplicate written pronunciation or alias: {term}")
        if not isinstance(pronunciation, str) or not pronunciation.strip():
            raise ValueError(f"missing written pronunciation: {term}")
        if not isinstance(references, list) or not references or any(
            not isinstance(reference, str) or not reference.startswith("https://") for reference in references
        ):
            raise ValueError(f"missing pronunciation reference: {term}")
        seen.add(term)
    return records
