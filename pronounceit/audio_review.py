from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


REVIEW_SCHEMA_VERSION = 2
REVIEW_SAMPLE_SEED = "pronounceit-v2-generated-sample"
REVIEW_SAMPLE_SIZE = 500
MIN_REVIEW_SCORE = 4

DRUG_SUFFIXES = (
    "cillin", "cycline", "floxacin", "mab", "nib", "olol", "pril", "sartan",
    "statin", "vir", "azole", "caine", "zepam", "oxetine", "apine", "gliptin",
)
ORGANISM_MARKERS = (
    "bacter", "bacillus", "coccus", "clostr", "escherich", "klebsiella", "mycobacter",
    "pseudomon", "staphyl", "strept", "virus", "fung", "candida", "plasmod",
)
ANATOMY_MARKERS = (
    "arter", "vein", "muscle", "nerve", "bone", "joint", "cerebr", "cardi", "hepat",
    "nephr", "pulmon", "gastr", "derm", "ophthalm", "uter", "ureter",
)
PATHOLOGY_MARKERS = (
    "itis", "osis", "emia", "oma", "pathy", "syndrome", "disease", "deficiency",
    "necrosis", "infection", "fracture", "stenosis", "thromb",
)


def empty_review_ledger(pack_version: str = "2") -> dict[str, Any]:
    return {
        "schemaVersion": REVIEW_SCHEMA_VERSION,
        "packVersion": pack_version,
        "sampleSeed": REVIEW_SAMPLE_SEED,
        "sampleSize": REVIEW_SAMPLE_SIZE,
        "methodApproval": None,
        "entries": [],
    }


def load_review_ledger(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty_review_ledger()
    if not isinstance(raw, dict) or raw.get("schemaVersion") != REVIEW_SCHEMA_VERSION:
        raise ValueError("unsupported audio review ledger")
    if not isinstance(raw.get("entries"), list):
        raise ValueError("audio review ledger entries must be a list")
    return raw


def review_ledger_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def method_binding_sha256(binding: dict[str, Any]) -> str:
    encoded = json.dumps(
        binding,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def method_approval_status(
    ledger: dict[str, Any],
    expected_binding: dict[str, Any],
) -> str:
    approval = ledger.get("methodApproval")
    if not isinstance(approval, dict):
        return "unapproved"
    binding = approval.get("binding")
    if not isinstance(binding, dict):
        return "invalid"
    stored_hash = str(approval.get("bindingSha256") or "").casefold()
    actual_hash = method_binding_sha256(binding)
    expected_hash = method_binding_sha256(expected_binding)
    if stored_hash != actual_hash or actual_hash != expected_hash:
        return "stale"
    if (
        approval.get("status") != "method-approved"
        or approval.get("scope") != "synthesis-method"
        or not str(approval.get("reviewer") or "").strip()
        or not str(approval.get("statement") or "").strip()
    ):
        return "invalid"
    return "method-approved"


def review_status(
    ledger: dict[str, Any],
    asset_id: str,
    audio_sha256: str,
) -> str:
    for entry in reversed(ledger.get("entries", [])):
        if not isinstance(entry, dict):
            continue
        if (
            str(entry.get("assetId") or "") != asset_id
            or str(entry.get("audioSha256") or "").casefold() != audio_sha256.casefold()
        ):
            continue
        accuracy = entry.get("accuracy")
        naturalness = entry.get("naturalness")
        if (
            entry.get("status") == "passed"
            and isinstance(accuracy, int)
            and isinstance(naturalness, int)
            and accuracy >= MIN_REVIEW_SCORE
            and naturalness >= MIN_REVIEW_SCORE
        ):
            return "passed"
        return "failed"
    return "unreviewed"


def term_categories(term: str) -> set[str]:
    normalized = " ".join(term.casefold().split())
    compact = normalized.replace(" ", "")
    categories: set[str] = set()
    if compact.endswith(DRUG_SUFFIXES):
        categories.add("drugs")
    if any(marker in compact for marker in ORGANISM_MARKERS):
        categories.add("organisms")
    if any(marker in compact for marker in ANATOMY_MARKERS):
        categories.add("anatomy")
    if any(marker in compact for marker in PATHOLOGY_MARKERS):
        categories.add("pathology")
    if "'s" in normalized or re.search(r"\b(von|van|de|la)\b", normalized):
        categories.add("eponyms")
    if compact.endswith(("us", "um", "ae", "ii", "is", "alis", "icus")):
        categories.add("latin")
    if " " in normalized:
        categories.add("multiword")
    length = len(compact)
    categories.add("short" if length <= 8 else "medium" if length <= 15 else "long")
    return categories


def deterministic_review_sample(
    terms: Iterable[str],
    size: int = REVIEW_SAMPLE_SIZE,
    seed: str = REVIEW_SAMPLE_SEED,
) -> list[str]:
    unique = sorted({str(term).strip() for term in terms if str(term).strip()}, key=str.casefold)

    def rank(term: str) -> str:
        return hashlib.sha256(f"{seed}\0{term.casefold()}".encode("utf-8")).hexdigest()

    ranked = sorted(unique, key=rank)
    buckets = (
        "drugs", "organisms", "anatomy", "pathology", "eponyms",
        "latin", "multiword", "short", "medium", "long",
    )
    quota = max(1, size // len(buckets))
    selected: list[str] = []
    selected_set: set[str] = set()
    for bucket in buckets:
        candidates = [term for term in ranked if bucket in term_categories(term)]
        for term in candidates:
            key = term.casefold()
            if key in selected_set:
                continue
            selected.append(term)
            selected_set.add(key)
            if sum(bucket in term_categories(item) for item in selected) >= quota:
                break
    for term in ranked:
        if len(selected) >= min(size, len(unique)):
            break
        if term.casefold() not in selected_set:
            selected.append(term)
            selected_set.add(term.casefold())
    return selected[:size]
