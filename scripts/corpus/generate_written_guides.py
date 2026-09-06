"""Offline generation for dictionary gaps. No output from here controls audio.

All results are explicitly AI Generated in internal provenance, including
AI-authored medical compositions, lexicon estimates, and rule-based G2P.
Generation is deterministic from checksummed inputs; linguistic accuracy is
not implied by a successful build or the provenance label.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import unicodedata

from scripts.corpus.written_phonetics import (
    VOWELS, from_arpabet, from_ipa, from_moby, render, render_respelling,
)


ROOT = Path(__file__).resolve().parents[2]
VERSION = "medical-written-gaps-v1"
# AI-authored US medical combining forms. Full segmentation is required;
# arbitrary leftover spellings are never treated as recognized medical roots.
ROOTS = {
    "aden": "ædən", "adeno": "ædənoʊ", "adip": "ædɪp", "adipo": "ædɪpoʊ",
    "angi": "ændʒi", "angio": "ændʒioʊ", "arthr": "ɑɹθɹ", "arthro": "ɑɹθɹoʊ",
    "bronch": "bɹɑŋk", "broncho": "bɹɑŋkoʊ", "cardi": "kɑɹdi", "cardio": "kɑɹdioʊ",
    "cephal": "sɛfəl", "cephalo": "sɛfəloʊ", "cerebr": "sɛɹəbɹ", "cerebro": "sɛɹəbɹoʊ",
    "cervic": "sɚvɪk", "cervico": "sɚvɪkoʊ", "chondr": "kɑndɹ", "chondro": "kɑndɹoʊ",
    "chole": "koʊlə", "choledocho": "koʊlɛdoʊkoʊ", "col": "koʊl", "colo": "koʊloʊ",
    "cyst": "sɪst", "cysto": "sɪstoʊ", "cyt": "saɪt", "cyto": "saɪtoʊ",
    "dacry": "dækɹi", "dacryo": "dækɹioʊ", "derm": "dɚm", "dermat": "dɚmət",
    "dermato": "dɚmətoʊ", "duoden": "duoʊdən", "duodeno": "duoʊdənoʊ",
    "encephal": "ɛnsɛfəl", "encephalo": "ɛnsɛfəloʊ", "enter": "ɛntɚ", "entero": "ɛntəɹoʊ",
    "esophag": "ɪsɑfəɡ", "esophago": "ɪsɑfəɡoʊ", "gastr": "ɡæstɹ", "gastro": "ɡæstɹoʊ",
    "gingiv": "dʒɪndʒɪv", "gingivo": "dʒɪndʒɪvoʊ", "glomerul": "ɡloʊmɛɹjʊl",
    "glomerulo": "ɡloʊmɛɹjʊloʊ", "gloss": "ɡlɑs", "glosso": "ɡlɑsoʊ",
    "glyc": "ɡlaɪk", "glyco": "ɡlaɪkoʊ", "hemat": "himət", "hemato": "himətoʊ",
    "hem": "him", "hemo": "himoʊ", "hepat": "hɛpət", "hepato": "hɛpətoʊ",
    "hyster": "hɪstɚ", "hystero": "hɪstəɹoʊ", "ile": "ɪli", "ileo": "ɪlioʊ",
    "ili": "ɪli", "ilio": "ɪlioʊ", "irid": "aɪɹɪd", "irido": "aɪɹɪdoʊ",
    "jejun": "dʒɪdʒun", "jejuno": "dʒɪdʒunoʊ", "kerat": "kɛɹət", "kerato": "kɛɹətoʊ",
    "laryng": "ləɹɪŋɡ", "laryngo": "ləɹɪŋɡoʊ", "leuk": "luk", "leuko": "lukoʊ",
    "lip": "lɪp", "lipo": "lɪpoʊ", "lith": "lɪθ", "litho": "lɪθoʊ",
    "lymph": "lɪmf", "lympho": "lɪmfoʊ", "mamm": "mæm", "mammo": "mæmoʊ",
    "mast": "mæst", "masto": "mæstoʊ", "mening": "mənɪndʒ", "meningo": "mənɪndʒoʊ",
    "myel": "maɪəl", "myelo": "maɪəloʊ", "my": "maɪ", "myo": "maɪoʊ",
    "nephr": "nɛfɹ", "nephro": "nɛfɹoʊ", "neur": "nʊɹ", "neuro": "nʊɹoʊ",
    "odont": "oʊdɑnt", "odonto": "oʊdɑntoʊ", "ophthalm": "ɑfθælm", "ophthalmo": "ɑfθælmoʊ",
    "oste": "ɑsti", "osteo": "ɑstioʊ", "ot": "oʊt", "oto": "oʊtoʊ",
    "pancreat": "pæŋkɹiət", "pancreato": "pæŋkɹiətoʊ", "pharyng": "fəɹɪŋɡ",
    "pharyngo": "fəɹɪŋɡoʊ", "phleb": "flɛb", "phlebo": "flɛboʊ",
    "pneum": "num", "pneumo": "numoʊ", "pneumon": "numən", "pneumono": "numənoʊ",
    "proct": "pɹɑkt", "procto": "pɹɑktoʊ", "pyel": "paɪəl", "pyelo": "paɪəloʊ",
    "pylor": "paɪlɔɹ", "pyloro": "paɪlɔɹoʊ", "rhabd": "ɹæbd", "rhabdo": "ɹæbdoʊ",
    "rhin": "ɹaɪn", "rhino": "ɹaɪnoʊ", "salping": "sælpɪŋɡ", "salpingo": "sælpɪŋɡoʊ",
    "scler": "sklɪɹ", "sclero": "sklɪɹoʊ", "sial": "saɪəl", "sialo": "saɪəloʊ",
    "splen": "splin", "spleno": "splinoʊ", "spondyl": "spɑndɪl", "spondylo": "spɑndɪloʊ",
    "ten": "tɛn", "teno": "tɛnoʊ", "thromb": "θɹɑmb", "thrombo": "θɹɑmboʊ",
    "trache": "tɹeɪki", "tracheo": "tɹeɪkioʊ", "ureter": "jʊɹitɚ", "uretero": "jʊɹitəɹoʊ",
    "urethr": "jʊɹiθɹ", "urethro": "jʊɹiθɹoʊ", "vas": "væs", "vaso": "væsoʊ",
    "ven": "vin", "veno": "vinoʊ", "vesic": "vɛsɪk", "vesico": "vɛsɪkoʊ",
}
PREFIXES = {
    "hyper": "haɪpɚ", "hypo": "haɪpoʊ", "micro": "maɪkɹoʊ", "macro": "mækɹoʊ",
    "intra": "ɪntɹə", "extra": "ɛkstɹə", "supra": "supɹə", "infra": "ɪnfɹə",
    "inter": "ɪntɚ", "trans": "tɹænz", "retro": "ɹɛtɹoʊ", "post": "poʊst",
    "pre": "pɹi", "sub": "səb", "non": "nɑn", "anti": "ænti", "auto": "ɔtoʊ",
    "allo": "æloʊ", "hetero": "hɛtəɹoʊ", "homo": "hoʊmoʊ", "iso": "aɪsoʊ",
    "hemi": "hɛmi", "semi": "sɛmi", "poly": "pɑli", "oligo": "ɑlɪɡoʊ",
    "para": "pæɹə", "peri": "pɛɹi", "meta": "mɛtə", "neo": "nioʊ",
    "endo": "ɛndoʊ", "ecto": "ɛktoʊ", "epi": "ɛpi", "pseudo": "sudoʊ",
    "dys": "dɪs", "eu": "ju", "a": "ə", "an": "æn",
}
# The stress-bearing suffix includes any vowel that shifts into primary stress.
SUFFIXES = {
    "itis": "ˈaɪtɪs", "itides": "ˈɪtɪdiz", "ectomy": "ˈɛktəmi",
    "ostomy": "ˈɑstəmi", "otomy": "ˈɑtəmi", "oplasty": "oʊˈplæsti",
    "orrhaphy": "ˈɔɹəfi", "orrhea": "əˈɹiə", "orrhoea": "əˈɹiə",
    "algia": "ˈældʒə", "dynia": "ˈdɪniə", "megaly": "ˈmɛɡəli",
    "penia": "ˈpiniə", "plegia": "ˈplidʒə", "paresis": "pəˈɹisɪs",
    "uria": "ˈjʊɹiə", "emia": "ˈimiə", "aemia": "ˈimiə",
    "osis": "ˈoʊsɪs", "oses": "ˈoʊsiz", "iasis": "ˈaɪəsɪs",
    "genic": "ˈdʒɛnɪk", "genesis": "ˈdʒɛnəsɪs", "opathy": "ˈɑpəθi",
    "ology": "ˈɑlədʒi", "ologist": "ˈɑlədʒɪst", "oscopy": "ˈɑskəpi",
    "ography": "ˈɑɡɹəfi", "malacia": "məˈleɪʃə", "phobia": "ˈfoʊbiə",
    "philia": "ˈfɪliə", "philic": "ˈfɪlɪk", "phagia": "ˈfeɪdʒə",
    "phasia": "ˈfeɪʒə", "esthesia": "ɛsˈθiʒə", "aesthesia": "ɛsˈθiʒə",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def model_ipa(value: str) -> str:
    # Misaki's documented en-US alphabet, without audio-engine stress changes.
    for old, new in (("A", "eɪ"), ("I", "aɪ"), ("O", "oʊ"), ("W", "aʊ"),
                     ("Y", "ɔɪ"), ("Q", "əʊ"), ("T", "t"), ("ᵻ", "ɪ"),
                     ("ʔ", "t"), ("x", "k"), ("ç", "k")):
        value = value.replace(old, new)
    return value


def as_ipa(words) -> str:
    # Keep syllable boundaries so adjacent vowels and onset /r/ do not turn
    # into diphthongs or rhotic vowels when the recorded IPA is read again.
    result = []
    for word, trace in zip(words, render(words)["conversion"]):
        syllables, position = [], 0
        for phones in trace["syllablePhones"]:
            part = word[position:position + len(phones)]
            stress = 1 if any(s == 1 for _, s in part) else 2 if any(s == 2 for _, s in part) else 0
            syllables.append({1: "ˈ", 2: "ˌ"}.get(stress, "") + "".join(phones))
            position += len(phones)
        result.append(".".join(syllables))
    return " ".join(result)


def phonetic_record(ipa: str, method: str, **details) -> dict:
    words = from_ipa(ipa)
    for word in words:
        # Unstressed fragments can occur in G2P. Keep all phones and explicitly
        # record inference of a citation-form stress, rather than dropping them.
        if word and not any(stress == 1 for _, stress in word):
            vowels = [i for i, (phone, _) in enumerate(word) if phone in VOWELS]
            if not vowels:
                raise ValueError("Generated word has no vowel")
            index = next((i for i in vowels if word[i][1] == 2), vowels[max(0, len(vowels) - 2)])
            word[index] = (word[index][0], 1)
            details["stressInferred"] = True
    ipa = as_ipa(words)
    return {**render(from_ipa(ipa)), "reviewStatus": "ai-generated", "provenance": {
        "kind": "ai-generated", "label": "AI Generated", "method": method,
        "alphabet": "ipa", "sourcePhonemes": ipa, **details}}


class Generator:
    def __init__(self, sources: Path, reference):
        from misaki.espeak import EspeakFallback
        import espeakng_loader
        self.reference = reference
        self.fallback = EspeakFallback(british=False)
        self.lexicons = {tier: json.loads((sources / f"us_{tier}.json").read_text()) for tier in ("gold", "silver")}
        overrides = ROOT / "data/written-guide-ai-overrides.json"
        self.overrides = json.loads(overrides.read_text())["terms"]
        self.lock = {"version": VERSION, "generatorSha256": sha(Path(__file__)),
                     "overridesSha256": sha(overrides), "misakiVersion": importlib.metadata.version("misaki"),
                     "phonemizerVersion": importlib.metadata.version("phonemizer-fork"),
                     "espeakVersion": str(self.fallback.backend.version()),
                     "espeakLibrarySha256": sha(Path(espeakng_loader.get_library_path())),
                     "espeakEnglishDictionarySha256": sha(Path(espeakng_loader.get_data_path()) / "en_dict"),
                     "files": {f"us_{tier}.json": sha(sources / f"us_{tier}.json") for tier in self.lexicons},
                     "humanReviewedAllTerms": False, "wholeLibraryAccuracyMeasured": False}

    def known_ipa(self, text):
        record = self.reference(text)
        if record:
            p = record["provenance"]
            decoders = {"ipa": from_ipa, "arpabet": from_arpabet, "moby": from_moby}
            if p.get("alphabet") in decoders:
                return as_ipa(decoders[p["alphabet"]](p["sourcePhonemes"])), p
        entry = self.lexicons["gold"].get(text)
        if isinstance(entry, str):
            return model_ipa(entry), {"kind": "misaki-gold-estimate"}
        return None

    @lru_cache(maxsize=None)
    def medical_parts(self, stem: str):
        if stem in ROOTS:
            return [(stem, ROOTS[stem])]
        for part in sorted(ROOTS.keys() | PREFIXES.keys(), key=lambda x: (-len(x), x)):
            if stem.startswith(part) and len(stem) > len(part):
                rest = self.medical_parts(stem[len(part):])
                if rest:
                    return [(part, ROOTS.get(part, PREFIXES.get(part))), *rest]
        return None

    def morphology(self, word: str):
        for suffix in sorted(SUFFIXES, key=lambda x: (-len(x), x)):
            if word.endswith(suffix):
                parts = self.medical_parts(word[:-len(suffix)])
                if parts:
                    stem_ipa = "".join(p for _, p in parts)
                    if suffix in {"itis", "itides"} and parts[-1][0] in {"laryng", "pharyng", "salping"}:
                        stem_ipa = stem_ipa[:-2] + "ndʒ"
                    return phonetic_record(stem_ipa + SUFFIXES[suffix],
                                           "medical-word-parts", segments=[x for x, _ in parts] + [suffix])
        prefixes = {**{k: v for k, v in ROOTS.items() if k.endswith("o")}, **PREFIXES}
        for prefix in sorted(prefixes, key=lambda x: (-len(x), x)):
            if len(prefix) < 3 or not word.startswith(prefix) or len(word) - len(prefix) < 5:
                continue
            base = word[len(prefix):]
            known = self.known_ipa(base)
            if known and len(from_ipa(known[0])) == 1:
                return phonetic_record(prefixes[prefix] + known[0], "medical-prefix-analogy",
                                       prefix=prefix, base=base, baseProvenance=known[1])
        # Suffixes that preserve citation-form stress and have stable phonology.
        candidates = []
        if word.endswith("'s"):
            candidates.append((word[:-2], "plural"))
        elif word.endswith("'"):
            candidates.append((word[:-1], "possessive-apostrophe"))
        if word.endswith("ies"):
            candidates.append((word[:-3] + "y", "plural"))
        if word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
            candidates.append((word[:-2], "plural"))
        if word.endswith("s"):
            candidates.append((word[:-1], "plural"))
        if word.endswith("ly"):
            candidates.append((word[:-2], "adverb"))
        for base, rule in candidates:
            if len(base) < 4:
                continue
            known = self.known_ipa(base)
            if not known:
                continue
            words = from_ipa(known[0])
            if len(words) != 1:
                continue
            last = words[0][-1][0]
            tail = "li" if rule == "adverb" else "" if rule == "possessive-apostrophe" else (
                "ɪz" if last in {"s", "z", "ʃ", "ʒ", "tʃ", "dʒ"} else
                "s" if last in {"p", "t", "k", "f", "θ"} else "z")
            return phonetic_record(known[0] + tail, "inflection-analogy", rule=rule,
                                   base=base, baseProvenance=known[1])
        return None

    @lru_cache(maxsize=None)
    def word(self, text: str) -> dict:
        word = normalized(text)
        override = self.overrides.get(text, self.overrides.get(word))
        if override:
            return {**render_respelling(override), "reviewStatus": "ai-generated", "provenance": {
                "kind": "ai-generated", "label": "AI Generated", "method": "ai-authored-medical-guide",
                "alphabet": "respelling", "sourcePhonemes": override, "inputText": text}}
        # Include optional combining-form letters, preserving the entire name.
        spelling = re.sub(r"[()]", "", word)
        if spelling in ROOTS:
            # Standalone combining forms generally retain root stress, rather
            # than stressing the unstressed linking vowel before a suffix.
            phones = from_ipa(ROOTS[spelling])[0]
            nuclei = [i for i, (phone, _) in enumerate(phones) if phone in VOWELS]
            if nuclei:
                index = nuclei[1] if spelling.startswith(("encephal", "ureter", "urethr", "duoden", "pharyng", "laryng")) and len(nuclei) > 1 else nuclei[0]
                phones[index] = (phones[index][0], 1)
            return phonetic_record(as_ipa([phones]), "medical-combining-form", inputText=text)
        for tier in ("gold", "silver"):
            if tier == "silver":
                derived = self.morphology(spelling)
                if derived:
                    return derived
            entry = self.lexicons[tier].get(spelling)
            if isinstance(entry, dict):
                entry = entry.get("DEFAULT") or entry.get("NN") or next((v for _, v in sorted(entry.items()) if isinstance(v, str)), None)
            if isinstance(entry, str):
                try:
                    return phonetic_record(model_ipa(entry), f"misaki-{tier}-estimate", inputText=text)
                except ValueError:
                    pass
        from types import SimpleNamespace
        # Punctuation is not spoken; letters and numeric identifiers remain.
        spelling = re.sub(r"[^a-z0-9' ]", "", spelling).strip("'")
        if not spelling:
            raise ValueError(f"Term has no readable letters or numbers: {text}")
        method = "espeak-us-word-rules"
        if spelling.isalpha() and not re.search("[aeiouy]", spelling):
            spelling = " ".join(spelling.upper())
            method = "spelled-letter-fragment"
        phones, _ = self.fallback(SimpleNamespace(text=spelling))
        decoded = from_ipa(model_ipa(phones or ""))
        if spelling.isalpha() and (not decoded or any(not any(p in VOWELS for p, _ in word) for word in decoded)):
            spelling = " ".join(spelling.upper())
            phones, _ = self.fallback(SimpleNamespace(text=spelling))
            method = "spelled-letter-fragment"
        try:
            return phonetic_record(model_ipa(phones or ""), method, inputText=text, generationText=spelling)
        except ValueError as exc:
            raise ValueError(f"Generation failed for {text!r} ({phones!r}): {exc}") from exc

    def __call__(self, term: str) -> dict:
        if term in self.overrides or normalized(term) in self.overrides:
            return self.word(term)
        parts = re.sub(r"[\u2010-\u2015-]+", " ", term).split()
        if len(parts) == 1:
            return self.word(parts[0])
        records = [(part, self.reference(part) or self.word(part)) for part in parts]
        return {"pronunciation": " ".join(p["pronunciation"] for _, p in records),
                "conversion": [trace for _, p in records for trace in p["conversion"]],
                "reviewStatus": "ai-generated", "provenance": {"kind": "ai-generated", "label": "AI Generated",
                "method": "phrase-components", "words": [{"word": part, **p["provenance"]} for part, p in records]}}
