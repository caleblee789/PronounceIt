"""Prepare immutable, auditable pronunciation inputs without generating audio."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from types import SimpleNamespace
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.audio_pack import audio_asset_id, file_sha256
from pronounceit.dictionary import DATA_FILE, normalize_term
from scripts.audio.kokoro_pilot import DEFAULT_OUTPUT as PILOT, SPEC, atomic_json, digest, read_json, verify, review_status
from scripts.corpus.phoneme_lexicon import CONSONANTS, VOWELS, render_record, validate_model_input

SOURCES = ROOT / "build/kokoro-source-snapshots"
PREPARED = ROOT / "build/kokoro-rebuild/prepared"
WIKI_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
WIKI_SIZE = 2826623319
WIKI_ETAG = '"6a916683-a87ad957"'
CMU_REVISION = "74790861f652b15e4ac49015a90074ad62a27690"
NUCLEI = frozenset("AIOWYauæɑɔəɛɜɪʊʌiᵻ")
MEDICAL = ("medical", "medicine", "anatom", "patholog", "pharmacol", "neurolog", "physiol", "surgery", "disease", "microbiolog")


def download(url: str, target: Path, *, size: int | None = None, etag: str | None = None) -> None:
    """Resume interrupted transfers; never join bytes from different snapshots."""
    receipt = target.with_suffix(target.suffix + ".receipt.json")
    if target.exists() and receipt.exists():
        saved = read_json(receipt)
        if saved["url"] == url and saved["sha256"] == file_sha256(target):
            return
        raise ValueError(f"Changed source snapshot: {target}")
    if target.exists():
        raise ValueError(f"Source has no integrity receipt: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(6):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            headers = {"User-Agent": "PronounceIt-local-rebuild/3"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
                if etag:
                    headers["If-Range"] = etag
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                if etag and response.headers.get("ETag") != etag:
                    raise ValueError("The upstream dictionary snapshot changed; refresh preparation before launching")
                append = offset > 0 and response.status == 206
                if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Invalid source download range")
                with partial.open("ab" if append else "wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
            if size is not None and partial.stat().st_size != size:
                raise OSError("Incomplete source download")
            checksum = file_sha256(partial)
            os.replace(partial, target)
            atomic_json(receipt, {"url": url, "sha256": checksum, "bytes": target.stat().st_size,
                                  "etag": etag, "retrievedAt": datetime.now(timezone.utc).isoformat()})
            return
        except (OSError, TimeoutError) as exc:
            if attempt == 5:
                raise
            print(f"Source transfer interrupted; retry {attempt + 1}/5: {exc}", flush=True)
            time.sleep(min(2 ** attempt, 20))


def fetch_sources() -> dict:
    SOURCES.mkdir(parents=True, exist_ok=True)
    download(WIKI_URL, SOURCES / "enwiktionary-20260805.jsonl.gz", size=WIKI_SIZE, etag=WIKI_ETAG)
    base = f"https://raw.githubusercontent.com/cmusphinx/cmudict/{CMU_REVISION}/"
    for filename in ("cmudict.dict", "LICENSE"):
        download(base + filename, SOURCES / ("cmudict-LICENSE" if filename == "LICENSE" else filename))
    import misaki
    package = Path(misaki.__file__).parent
    for filename in ("us_gold.json", "us_silver.json"):
        target = SOURCES / filename
        if target.exists() and file_sha256(target) != file_sha256(package / "data" / filename):
            raise ValueError("Installed Misaki dictionary differs from its saved snapshot")
        if not target.exists():
            shutil.copy2(package / "data" / filename, target)
    lock = {
        "schemaVersion": 1, "wiktionaryDumpDate": "2026-08-05", "wiktextractExtractionDate": "2026-08-28",
        "wiktextractRevision": "872fc7b", "cmudictRevision": CMU_REVISION,
        "misakiVersion": importlib.metadata.version("misaki"),
        "files": {p.name: file_sha256(p) for p in sorted(SOURCES.iterdir()) if p.name in
                  {"enwiktionary-20260805.jsonl.gz", "cmudict.dict", "cmudict-LICENSE", "us_gold.json", "us_silver.json"}},
    }
    atomic_json(SOURCES / "sources.lock.json", lock)
    return lock


def word_texts(term: str) -> list[str]:
    return re.sub(r"[\u2010-\u2015-]+", " ", term).split()


def word_coverage_key(term: str) -> str:
    # Preserve optional affix letters; the lookup normalizer intentionally
    # removes trailing parenthetical aliases and is unsuitable for this check.
    return " ".join(word_texts(term)).casefold()


def build_wiki_index(items: list[dict], lock: dict) -> dict:
    target = SOURCES / "pronunciation-index.json"
    keys = {normalize_term(text) for item in items for text in
            [item["term"], *item.get("aliases", []), *word_texts(item["term"])]}
    binding = digest({"keys": sorted(keys), "source": lock["files"]["enwiktionary-20260805.jsonl.gz"]})
    if target.exists():
        saved = read_json(target)
        if saved["bindingSha256"] == binding:
            return saved["entries"]
        raise ValueError("Wiktionary index belongs to different input terms")
    entries: dict[str, list[dict]] = {}
    with gzip.open(SOURCES / "enwiktionary-20260805.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            # Avoid parsing the much larger collection of other languages.
            if '"lang_code": "en"' not in line and '"lang_code":"en"' not in line:
                continue
            row = json.loads(line)
            key = normalize_term(row.get("word", ""))
            if row.get("lang_code") != "en" or key not in keys:
                continue
            medical = any(marker in json.dumps(row.get("senses", [])).casefold() for marker in MEDICAL)
            for sound in row.get("sounds", []):
                tags = sound.get("tags", [])
                us = any(t in {"US", "General-American", "American", "American-English"} for t in tags)
                if not us or not sound.get("ipa"):
                    continue
                candidate = {"ipa": sound["ipa"], "tags": tags, "medical": medical,
                             "url": "https://en.wiktionary.org/wiki/" + urllib.parse.quote(row["word"].replace(" ", "_")),
                             "sourceLine": line_number}
                group = entries.setdefault(key, [])
                if not any(x["ipa"] == candidate["ipa"] and x["medical"] == medical for x in group):
                    group.append(candidate)
    atomic_json(target, {"bindingSha256": binding, "entries": entries})
    print(f"Indexed US dictionary pronunciations for {len(entries):,} matching terms/words", flush=True)
    return entries


def engine_stress(phones: str) -> str:
    return re.sub(r"([ˈˌ])([^" + "".join(NUCLEI) + r"\sˈˌ]*)([" + "".join(NUCLEI) + r"])", r"\2\1\3", phones)


def ipa_to_kokoro(ipa: str, vocab: dict) -> str:
    phones = ipa.strip().strip("/[]")
    for old, new in (("t͡ʃ", "ʧ"), ("d͡ʒ", "ʤ"), ("tʃ", "ʧ"), ("dʒ", "ʤ"),
                     ("aɪ", "I"), ("aʊ", "W"), ("eɪ", "A"), ("ɔɪ", "Y"), ("oʊ", "O"),
                     ("ɝ", "ɜɹ"), ("ɚ", "əɹ"), ("ɫ", "l"), ("ɾ", "T"), ("g", "ɡ"),
                     ("r", "ɹ"), ("ɐ", "ə"), ("l̩", "əl"), ("n̩", "ən"), ("m̩", "əm")):
        phones = phones.replace(old, new)
    phones = re.sub(r"[.ːˑ()]", "", phones)
    phones = engine_stress(" ".join(phones.split()))
    validate_model_input(phones, vocab)
    if not any(c in NUCLEI for c in phones):
        raise ValueError("Pronunciation has no vowel")
    return phones


def arpabet_to_kokoro(raw: str, vocab: dict) -> str:
    result = []
    for token in raw.split():
        match = re.fullmatch(r"([A-Z]+)([012]?)", token)
        if not match:
            raise ValueError(f"Invalid ARPABET token: {token}")
        base, stress = match.groups()
        if base in VOWELS and stress:
            phone = VOWELS[base][0]
            if base == "AH" and stress == "0": phone = "ə"
            if base == "ER" and stress == "0": phone = "əɹ"
            result.append({"0": "", "1": "ˈ", "2": "ˌ"}[stress] + phone)
        elif base in CONSONANTS and not stress:
            result.append(CONSONANTS[base][0])
        else:
            raise ValueError(f"Unsupported ARPABET token: {token}")
    phones = "".join(result)
    validate_model_input(phones, vocab)
    return phones


def load_cmu() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in (SOURCES / "cmudict.dict").read_text().splitlines():
        if not line or line.startswith(";;;"): continue
        word, phones = line.split(maxsplit=1)
        word = re.sub(r"\(\d+\)$", "", word)
        result.setdefault(normalize_term(word), []).append(phones.split(" #", 1)[0])
    return result


def manual_correction(item: dict, vocab: dict) -> list[dict] | None:
    segments = item.get("sapiSegments") or item.get("sapi_segments")
    if not segments:
        sapi = item.get("sapiPhonemes") or item.get("sapi_phonemes")
        segments = [{"text": item["term"], "sapi": sapi}] if sapi else []
    if not segments:
        return None
    words = []
    for segment in segments:
        source = segment["sapi"]
        tokens = source.replace("-", " ").split()
        arpa = []
        for index, token in enumerate(tokens):
            if token in {"0", "1", "2"}: continue
            base = token.upper()
            if base == "AX": base = "AH"
            if base in VOWELS:
                stress = tokens[index + 1] if index + 1 < len(tokens) and tokens[index + 1] in {"0", "1", "2"} else "0"
                base += stress
            arpa.append(base)
        words.append({"text": segment["text"], "phonemes": arpabet_to_kokoro(" ".join(arpa), vocab),
                      "provenance": {"kind": "preserved-manual-correction", "referenceBacked": True, "sourcePhonemes": source}})
    return words


def prepare() -> dict:
    pilot = verify(PILOT)
    if not review_status(PILOT, pilot)["fullGenerationApproved"]:
        raise ValueError("The exact revised Kokoro pilot must be accepted first")
    items = read_json(DATA_FILE)["terms"]
    if len(items) != 95902 or len({audio_asset_id(x["term"]) for x in items}) != 95902:
        raise ValueError("The canonical 95,902-term list changed")
    lock = read_json(SOURCES / "sources.lock.json")
    for name, checksum in lock["files"].items():
        if file_sha256(SOURCES / name) != checksum:
            raise ValueError(f"Source checksum mismatch: {name}")
    binding = digest({"dictionary": file_sha256(DATA_FILE), "sources": lock,
                      "pilot": pilot["bindingSha256"], "builder": file_sha256(Path(__file__))})
    if (PREPARED / "prepared.json").exists():
        saved = read_json(PREPARED / "prepared.json")
        if saved["bindingSha256"] == binding and file_sha256(PREPARED / "pronunciations.jsonl") == saved["recordsSha256"]:
            return saved
        raise ValueError("Prepared pronunciation inputs changed; preserve the previous run before preparing again")
    PREPARED.mkdir(parents=True, exist_ok=True)
    wiki = build_wiki_index(items, lock)
    cmu = load_cmu()
    gold, silver = (read_json(SOURCES / f"us_{tier}.json") for tier in ("gold", "silver"))
    from misaki.espeak import EspeakFallback
    fallback = EspeakFallback(british=False)
    config = ROOT / "build/kokoro-model-cache/models--hexgrad--Kokoro-82M/snapshots" / read_json(SPEC)["method"]["modelRevision"] / "config.json"
    vocab = read_json(config)["vocab"]
    pilots = {normalize_term(x["term"]): x for x in pilot["entries"]}
    counts: Counter = Counter()
    conflicts, failures, records = [], [], []

    def select(text: str, allow_estimate: bool = True) -> tuple[str, dict] | None:
        key = normalize_term(text)
        candidates = wiki.get(key, [])
        for medical in (True, False):
            if not medical:
                versions = cmu.get(key, [])
                if versions and len({re.sub(r"[012]", "", v) for v in versions}) == 1:
                    return arpabet_to_kokoro(versions[0], vocab), {"kind": "cmudict", "referenceBacked": True,
                        "revision": CMU_REVISION, "sourcePhonemes": versions[0]}
            for candidate in candidates:
                if candidate["medical"] != medical: continue
                try: phones = ipa_to_kokoro(candidate["ipa"], vocab)
                except ValueError: continue
                if len(phones.split()) < len(word_texts(text)): continue
                return phones, {"kind": "wiktionary-us", "referenceBacked": True, **candidate,
                                "acceptedVariants": sorted({x["ipa"] for x in candidates})}
        if not allow_estimate: return None
        for tier, data in (("gold", gold), ("silver", silver)):
            entry = data.get(text, data.get(text.lower()))
            if isinstance(entry, dict):
                options = {v for v in entry.values() if isinstance(v, str)}
                entry = next(iter(options)) if len(options) == 1 else None
            if isinstance(entry, str):
                phones = engine_stress(entry.replace("ɾ", "T").replace("ʔ", "t"))
                try: validate_model_input(phones, vocab)
                except ValueError: continue
                return phones, {"kind": f"misaki-{tier}-estimate", "referenceBacked": False}
        phones, _ = fallback(SimpleNamespace(text=text))
        phones = engine_stress(phones or "")
        validate_model_input(phones, vocab)
        if not any(c in NUCLEI for c in phones):
            # Preserve unreadable source name fragments as explicit estimates.
            if not text.isalpha():
                raise ValueError(f"No spoken vowel for {text}")
            phones, _ = fallback(SimpleNamespace(text=" ".join(text.upper())))
            phones = engine_stress(phones or "")
            validate_model_input(phones, vocab)
            if not any(c in NUCLEI for c in phones):
                raise ValueError(f"No spoken vowel for spelled fragment {text}")
            return phones, {"kind": "spelled-fragment-estimate", "referenceBacked": False,
                            "needsReview": "Source spelling has no pronounceable vowel; letters spoken individually"}
        return phones, {"kind": "espeak-estimate", "referenceBacked": False}

    for position, item in enumerate(items, 1):
        term = item["term"]
        try:
            accepted = pilots.get(normalize_term(term))
            if accepted:
                words = [{"text": term, "phonemes": accepted["phonemes"],
                          "provenance": {"kind": "listening-approved-pilot", "referenceBacked": True,
                                         "pilotBindingSha256": pilot["bindingSha256"], "sources": accepted["sources"]}}]
                quality = "listening-approved"
            else:
                correction = manual_correction(item, vocab)
                exact = None if correction else select(term, allow_estimate=False)
                if correction:
                    words = correction
                elif exact:
                    phones, provenance = exact
                    words = [{"text": term, "phonemes": phones, "provenance": provenance}]
                else:
                    words = []
                    for text in word_texts(term):
                        phones, provenance = select(text)
                        words.append({"text": text, "phonemes": phones, "provenance": provenance})
                quality = "reference-backed" if all(w["provenance"]["referenceBacked"] for w in words) else "unverified-estimate"
            if word_coverage_key(" ".join(w["text"] for w in words)) != word_coverage_key(term):
                raise ValueError("Word coverage changed")
            phones = " ".join(w["phonemes"] for w in words)
            validate_model_input(phones, vocab)
            record = {"schemaVersion": 1, "term": term, "assetId": audio_asset_id(term),
                      "aliases": item.get("aliases", []), "phonemeAlphabet": "kokoro-us-v1",
                      "phonemes": phones, "words": words, "wordBoundaries": [i for i, c in enumerate(phones) if c == " "],
                      "stress": [{"position": i, "level": "primary" if c == "ˈ" else "secondary"}
                                 for i, c in enumerate(phones) if c in "ˈˌ"],
                      "reviewStatus": quality, "clipReviewStatus": "accepted" if accepted else "unreviewed"}
            record["phonemeInputSha256"] = digest({"alphabet": record["phonemeAlphabet"], "words": words})
            records.append(record)
            counts[quality] += 1
            for word in words:
                variants = word["provenance"].get("acceptedVariants", [])
                if len(variants) > 1:
                    conflicts.append({"term": term, "word": word["text"], "status": "accepted-source-variants", "variants": variants})
        except (ValueError, TypeError) as exc:
            failures.append({"term": term, "error": str(exc)})
        if position % 5000 == 0:
            print(f"Prepared {position:,}/95,902 pronunciation inputs; unresolved={len(failures)}", flush=True)
    atomic_json(PREPARED / "unresolved.json", failures)
    atomic_json(PREPARED / "source-variants.json", conflicts)
    if failures:
        raise ValueError(f"{len(failures)} terms require input correction before the overnight run; see {PREPARED / 'unresolved.json'}")
    output = PREPARED / "pronunciations.jsonl"
    temporary = output.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records: handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(temporary, output)
    shutil.copy2(DATA_FILE, PREPARED / "original-dictionary.json")
    shutil.copy2(SPEC, PREPARED / "pilot-spec.json")
    shutil.copy2(PILOT / "pilot-manifest.json", PREPARED / "pilot-manifest.json")
    shutil.copy2(PILOT / "acceptance.json", PREPARED / "pilot-acceptance.json")
    saved = {"schemaVersion": 1, "bindingSha256": binding, "recordsSha256": file_sha256(output),
             "originalDictionarySha256": file_sha256(DATA_FILE), "pilotBindingSha256": pilot["bindingSha256"],
             "termCount": len(records), "qualityCounts": dict(counts), "acceptedVariantRecords": len(conflicts),
             "sources": lock, "createdAt": datetime.now(timezone.utc).isoformat(),
             "audioGenerated": False, "releaseReady": False}
    atomic_json(PREPARED / "prepared.json", saved)
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "prepare"])
    args = parser.parse_args()
    print(json.dumps(fetch_sources() if args.command == "fetch" else prepare(), indent=2))
