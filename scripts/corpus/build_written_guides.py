"""Rebuild display-only guides: dictionary references, then internally marked AI generation."""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.written_guides import canonical_terms_sha256, load_written_guides
from pronounceit.written_phonetics import from_arpabet, from_ipa, from_moby, render, render_respelling

MEDICAL = ("medicine", "medical", "anatom", "patholog", "pharmacol", "physiol", "surgery")
EXCLUDED = ("obsolete", "archaic", "nonstandard", "non-standard", "mispronunciation")
US = {"us", "general-american", "american", "american-english"}
REGIONAL = {"uk", "us", "received-pronunciation", "british", "british-english", "australia",
            "australian", "canada", "canadian", "new-zealand", "ireland", "scotland", "england",
            "south-africa", "india", "irish", "scottish", "general-american", "american"}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def key(text: str) -> str:
    # Do not strip parenthetical name fragments or use synonym aliases as sounds.
    return " ".join(re.sub(r"[\u2010-\u2015-]+", " ", text).casefold().split())


def components(text: str) -> list[str]:
    return re.sub(r"[\u2010-\u2015-]+", " ", text).split()


def rank(candidate: dict) -> tuple:
    tags = {x.casefold() for x in candidate["tags"]}
    accent = 0 if tags & US else 2 if tags & REGIONAL else 1
    return (not candidate["medical"], accent, candidate["sourceLine"], candidate["variantIndex"])


def index_wiktionary(items: list[dict], sources: Path, lock: dict, cache: Path) -> dict:
    name = next(n for n in lock["files"] if n.endswith(".jsonl.gz"))
    binding = {"schemaVersion": 2, "canonicalTermsSha256": canonical_terms_sha256(items),
               "sourceSha256": lock["files"][name]}
    if cache.exists():
        saved = read(cache)
        if saved.get("binding") == binding:
            return saved["entries"]
        raise ValueError("Existing text index belongs to different inputs; use a new cache path")
    keys = {key(t) for item in items for t in [item["term"], *components(item["term"])]}
    entries = {}
    with gzip.open(sources / name, "rt", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if '"lang_code": "en"' not in line and '"lang_code":"en"' not in line:
                continue
            row = json.loads(line)
            term_key = key(row.get("word", ""))
            if row.get("lang_code") != "en" or term_key not in keys:
                continue
            senses = row.get("senses", [])
            if senses and all(any(t.casefold() in EXCLUDED for t in s.get("tags", [])) for s in senses):
                continue
            medical = any(marker in json.dumps(senses).casefold() for marker in MEDICAL)
            for variant, sound in enumerate(row.get("sounds", [])):
                tags = sound.get("tags", [])
                if not sound.get("ipa") or any(x in " ".join(tags).casefold() for x in EXCLUDED):
                    continue
                candidate = {"ipa": sound["ipa"], "tags": tags, "medical": medical,
                             "url": "https://en.wiktionary.org/wiki/" + urllib.parse.quote(row["word"].replace(" ", "_")),
                             "sourceLine": number, "variantIndex": variant}
                group = entries.setdefault(term_key, [])
                if candidate not in group:
                    group.append(candidate)
    write(cache, {"binding": binding, "entries": entries})
    print(f"Indexed {len(entries):,} matching headwords/components", flush=True)
    return entries


def build(data: Path, sources: Path, corrections_path: Path, output: Path, report: Path, cache: Path,
          supplemental: Path | None = None, generate: bool = True) -> dict:
    items = read(data)["terms"]
    lock = read(sources / "sources.lock.json")
    # Only the two dictionaries are inputs; audio model lexicons are never used.
    source_files = {n: h for n, h in lock["files"].items()
                    if n.endswith(".jsonl.gz") or n in {"cmudict.dict", "cmudict-LICENSE"}}
    for name, checksum in source_files.items():
        if sha(sources / name) != checksum:
            raise ValueError(f"Changed source snapshot: {name}")
    wiki = index_wiktionary(items, sources, lock, cache)
    cmu = {}
    for line in (sources / "cmudict.dict").read_text().splitlines():
        if not line or line.startswith(";;;"):
            continue
        word, phones = line.split(maxsplit=1)
        word = re.sub(r"\(\d+\)$", "", word)
        cmu.setdefault(key(word), []).append(phones.split(" #", 1)[0])
    correction_items = read(corrections_path)["terms"]
    corrections = {x["term"]: x for x in correction_items}
    if len(corrections) != len(correction_items) or not corrections.keys() <= {x["term"] for x in items}:
        raise ValueError("Duplicate or unknown correction term")
    rejections = Counter()
    supplemental_lock, nci, moby = {}, {}, {}
    if supplemental is not None:
        supplemental_lock = read(supplemental / "sources.lock.json")
        for name, receipt in supplemental_lock["files"].items():
            if sha(supplemental / name) != receipt["sha256"]:
                raise ValueError(f"Changed supplemental snapshot: {name}")
        for row in read(supplemental / "nci-terms.json"):
            if row.get("language") == "en" and (row.get("pronunciation") or {}).get("key"):
                nci.setdefault(key(row["termName"]), []).append(row)
        for number, line in enumerate((supplemental / "mpron.txt").read_text(encoding="mac_roman").splitlines(), 1):
            if not line.strip():
                continue
            word, phones = line.split(maxsplit=1)
            word = re.sub(r"/(?:n|v|av|aj|interj)$", "", word).replace("_", " ")
            moby.setdefault(key(word), []).append((number, phones))

    @lru_cache(maxsize=None)
    def extra_reference(text: str):
        for row in nci.get(key(text), []):
            try:
                rendered = render_respelling(row["pronunciation"]["key"])
                if len(rendered["conversion"]) != len(text.split()):
                    raise ValueError("Source word boundaries differ from term")
            except ValueError as exc:
                rejections[str(exc)] += 1
                continue
            url = "https://www.cancer.gov/publications/dictionaries/cancer-terms/def/" + (row.get("prettyUrlName") or str(row["termId"]))
            return {**rendered, "reviewStatus": "reference-backed", "provenance": {
                "kind": "nci", "references": [url], "alphabet": "respelling",
                "sourcePhonemes": row["pronunciation"]["key"], "termId": row["termId"],
                "retrievedAt": supplemental_lock["retrievedAt"]}}
        for number, phones in moby.get(key(text), []):
            try:
                rendered = render(from_moby(phones))
                if len(rendered["conversion"]) != len(text.split()):
                    raise ValueError("Source word boundaries differ from term")
            except ValueError as exc:
                rejections[str(exc).split(":", 1)[0]] += 1
                continue
            return {**rendered, "reviewStatus": "reference-backed", "provenance": {
                "kind": "moby", "references": ["https://www.gutenberg.org/files/3205/files/mpron.txt"],
                "alphabet": "moby", "sourcePhonemes": phones, "sourceLine": number,
                "retrievedAt": supplemental_lock["retrievedAt"]}}
        return None

    @lru_cache(maxsize=None)
    def reference(text: str):
        for candidate in sorted(wiki.get(key(text), []), key=rank):
            try:
                words = from_ipa(candidate["ipa"])
                if len(words) != len(text.split()):
                    raise ValueError("Source word boundaries differ from term")
                rendered = render(words)
            except ValueError as exc:
                rejections[str(exc).split(":", 1)[0]] += 1
                continue
            return {**rendered, "reviewStatus": "reference-backed", "provenance": {
                "kind": "wiktionary", "references": [candidate["url"]],
                "alphabet": "ipa", "sourcePhonemes": candidate["ipa"],
                "tags": candidate["tags"], "medical": candidate["medical"],
                "sourceLine": candidate["sourceLine"], "variantIndex": candidate["variantIndex"],
                "snapshot": lock["wiktionaryDumpDate"]}}
        # CMUdict only supplies complete single-word entries.
        if len(text.split()) == 1:
            for variant, phones in enumerate(cmu.get(key(text), [])):
                try:
                    rendered = render(from_arpabet(phones))
                except ValueError as exc:
                    rejections[str(exc).split(":", 1)[0]] += 1
                    continue
                return {**rendered, "reviewStatus": "reference-backed", "provenance": {
                    "kind": "cmudict", "references": [f"https://github.com/cmusphinx/cmudict/blob/{lock['cmudictRevision']}/cmudict.dict"],
                    "alphabet": "arpabet", "sourcePhonemes": phones,
                    "revision": lock["cmudictRevision"], "variantIndex": variant}}
        return None

    def composed(term: str, lookup):
        if len(components(term)) < 2:
            return None
        parts = [(word, lookup(word)) for word in components(term)]
        if not all(part for _, part in parts):
            return None
        return {"pronunciation": " ".join(part["pronunciation"] for _, part in parts),
                "conversion": [trace for _, part in parts for trace in part["conversion"]],
                "reviewStatus": "composed", "provenance": {"kind": "composed-guide",
                "words": [{"word": word, **part["provenance"]} for word, part in parts],
                "references": list(dict.fromkeys(url for _, part in parts for url in part["provenance"]["references"]))}}

    generator = None
    if generate:
        from scripts.corpus.generate_written_guides import Generator
        generator = Generator(sources, lambda text: reference(text) or extra_reference(text))
    records, counts, unresolved, generated_methods = [], Counter(), [], Counter()
    for number, item in enumerate(items, 1):
        term = item["term"]
        record = reference(term)
        if record is None:
            record = composed(term, reference)
        if term in corrections and (record is None or corrections[term].get("overrideReference")):
            correction = corrections[term]
            if not correction.get("references") or not correction.get("pronunciation"):
                raise ValueError(f"Undocumented correction: {term}")
            record = {"pronunciation": correction["pronunciation"], "reviewStatus": "documented-correction",
                      "provenance": {"kind": "documented-correction", "references": correction["references"],
                                     "reason": correction["reason"]}}
        if record is None:
            record = extra_reference(term) or composed(term, lambda word: reference(word) or extra_reference(word))
        if record is None and generator is not None:
            record = generator(term)
            generated_methods[record["provenance"]["method"]] += 1
        if record is None:
            record = {"pronunciation": "", "reviewStatus": "unavailable", "provenance": {
                "kind": "unavailable", "reason": "No complete supported pronunciation in the selected references"}}
            unresolved.append(term)
        record = {"term": term, **record}
        counts[record["provenance"]["kind"]] += 1
        records.append(record)
        if number % 5000 == 0:
            print(f"Prepared {number:,}/{len(items):,} written guides", flush=True)
    result = {"schemaVersion": 2, "canonicalTermsSha256": canonical_terms_sha256(items),
              "sourceLock": {"files": source_files, "wiktionaryDumpDate": lock["wiktionaryDumpDate"],
                             "wiktextractExtractionDate": lock["wiktextractExtractionDate"],
                             "wiktextractRevision": lock["wiktextractRevision"], "cmudictRevision": lock["cmudictRevision"]},
              "correctionsSha256": sha(corrections_path), "converterSha256": sha(ROOT / "pronounceit/written_phonetics.py"),
              "builderSha256": sha(Path(__file__)), "supplementalSourceLock": supplemental_lock,
              "generationLock": generator.lock if generator else None, "terms": records}
    write(output, result)
    load_written_guides(output, items)
    from pronounceit.written_guides import audit_written_sources
    audit_written_sources(output, items, corrections_path)
    summary = {"termCount": len(records), "counts": dict(counts),
               "available": len(records) - len(unresolved), "unavailable": len(unresolved),
               "changedGuides": sum(x["pronunciation"] != y.get("pronunciation") for x, y in zip(records, items)),
               "baseDictionarySha256": sha(data), "writtenGuidesSha256": sha(output),
               "sourceLock": result["sourceLock"], "unresolvedTerms": unresolved,
               "generatedMethods": dict(generated_methods),
               "rejectedSourceConversions": dict(rejections), "wholeLibraryAccuracyMeasured": False}
    write(report, summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"unresolvedTerms", "sourceLock", "rejectedSourceConversions"}}, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/medical_pronunciations.json")
    parser.add_argument("--sources", type=Path, default=ROOT / "build/kokoro-source-snapshots")
    parser.add_argument("--corrections", type=Path, default=ROOT / "data/written-guide-corrections.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/written_pronunciations.json")
    parser.add_argument("--report", type=Path, default=ROOT / "build/written-guides/coverage.json")
    parser.add_argument("--index", type=Path, default=ROOT / "build/written-guides/wiktionary-index.json")
    parser.add_argument("--supplemental", type=Path, default=ROOT / "build/written-guide-sources")
    parser.add_argument("--references-only", action="store_true", help="Audit reference coverage without generating gaps")
    args = parser.parse_args()
    build(args.data, args.sources, args.corrections, args.output, args.report, args.index, args.supplemental,
          generate=not args.references_only)
