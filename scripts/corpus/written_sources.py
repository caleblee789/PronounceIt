"""Reference-backed display text, independent of pronunciation audio inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


STATUSES = {"reference-backed", "composed", "documented-correction", "ai-generated", "unavailable"}


def canonical_terms_sha256(items: list[dict]) -> str:
    identities = [{"term": x["term"], "aliases": x.get("aliases", [])} for x in items]
    return hashlib.sha256(json.dumps(identities, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_written_guides(path: Path, items: list[dict]) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 2:
        raise ValueError("unsupported written-guide schema")
    if raw.get("canonicalTermsSha256") != canonical_terms_sha256(items):
        raise ValueError("written guides belong to different terms or aliases")
    records = raw.get("terms")
    if not isinstance(records, list) or len(records) != len(items):
        raise ValueError("incomplete written-guide inventory")
    result = {}
    for record, item in zip(records, items):
        if not isinstance(record, dict) or record.get("term") != item["term"]:
            raise ValueError("written-guide canonical order differs")
        if record["term"] in result:
            raise ValueError("duplicate written-guide term")
        status = record.get("reviewStatus")
        guide = record.get("pronunciation")
        if status not in STATUSES or not isinstance(guide, str):
            raise ValueError("invalid written guide")
        if (status == "unavailable") != (not guide.strip()):
            raise ValueError("written-guide availability differs from text")
        provenance = record.get("provenance")
        if not isinstance(provenance, dict) or not provenance.get("kind"):
            raise ValueError("missing written-guide provenance")
        if status == "ai-generated" and (provenance.get("kind") != "ai-generated" or
                                         provenance.get("label") != "AI Generated" or not provenance.get("method")):
            raise ValueError("generated guide has no internal generation provenance")
        if status not in {"unavailable", "ai-generated"} and not provenance.get("references"):
            raise ValueError("written guide has no reference")
        result[record["term"]] = record
    return result


def audit_written_sources(path: Path, items: list[dict], corrections_path: Path) -> None:
    """Re-render selected dictionary sounds; structural success is not linguistic approval."""
    from .written_phonetics import from_arpabet, from_ipa, from_moby, render, render_respelling

    raw = json.loads(path.read_text(encoding="utf-8"))
    guides = load_written_guides(path, items)
    corrections_bytes = corrections_path.read_bytes()
    if hashlib.sha256(corrections_bytes).hexdigest() != raw.get("correctionsSha256"):
        raise ValueError("documented corrections changed after generation")
    corrections = {x["term"]: x for x in json.loads(corrections_bytes)["terms"]}
    if any(x["reviewStatus"] == "ai-generated" for x in guides.values()):
        overrides_path = corrections_path.with_name("written-guide-ai-overrides.json")
        generation = raw.get("generationLock") or {}
        if hashlib.sha256(overrides_path.read_bytes()).hexdigest() != generation.get("overridesSha256"):
            raise ValueError("AI-authored corrections changed after generation")
        if not generation.get("version") or not generation.get("generatorSha256"):
            raise ValueError("missing generation manifest")

    def converted(provenance):
        alphabet = provenance["alphabet"]
        if alphabet == "arpabet":
            words = from_arpabet(provenance["sourcePhonemes"])
        elif alphabet == "ipa":
            words = from_ipa(provenance["sourcePhonemes"])
        elif alphabet == "moby":
            words = from_moby(provenance["sourcePhonemes"])
        elif alphabet == "respelling":
            return render_respelling(provenance["sourcePhonemes"])
        else:
            raise ValueError("unsupported source alphabet")
        return render(words)

    for term, guide in guides.items():
        status, provenance = guide["reviewStatus"], guide["provenance"]
        if status == "unavailable":
            continue
        if status == "documented-correction":
            correction = corrections.get(term)
            if not correction or provenance["references"] != correction["references"]:
                raise ValueError(f"Undocumented correction: {term}")
            expected = {"pronunciation": correction["pronunciation"]}
        elif status == "ai-generated" and provenance.get("alphabet"):
            expected = converted(provenance)
        elif status == "reference-backed":
            expected = converted(provenance)
            if len(expected["conversion"]) != len(term.split()):
                raise ValueError(f"Source word coverage differs: {term}")
        else:
            import re
            parts = provenance["words"]
            coverage = lambda text: " ".join(re.sub(r"[\u2010-\u2015-]+", " ", text).split())
            if coverage(" ".join(p["word"] for p in parts)) != coverage(term):
                raise ValueError(f"Composed guide omitted a word: {term}")
            rendered = [converted(p) for p in parts]
            expected = {"pronunciation": " ".join(p["pronunciation"] for p in rendered),
                        "conversion": [c for p in rendered for c in p["conversion"]]}
        if any(guide.get(k) != value for k, value in expected.items()):
            raise ValueError(f"Guide differs from selected source: {term}")
