"""Strict phoneme-to-readable-text conversion, independent of the audio engine."""
from __future__ import annotations

import re
import unicodedata

VOWELS = {"ɑ": "ah", "æ": "a", "ʌ": "uh", "ə": "uh", "ɔ": "aw", "aʊ": "ow",
          "aɪ": "eye", "ɛ": "eh", "ɝ": "ur", "ɚ": "er", "eɪ": "ay", "ɪ": "ih",
          "i": "ee", "oʊ": "oh", "əʊ": "oh", "ɔɪ": "oy", "ʊ": "uu", "u": "oo",
          "ɒ": "o", "ɜ": "ur", "e": "eh", "a": "a", "ɐ": "uh"}
CONSONANTS = {"b": "b", "tʃ": "ch", "d": "d", "ð": "th", "f": "f", "ɡ": "g",
              "h": "h", "dʒ": "j", "k": "k", "l": "l", "m": "m", "n": "n",
              "ŋ": "ng", "p": "p", "ɹ": "r", "s": "s", "ʃ": "sh", "t": "t",
              "θ": "th", "v": "v", "w": "w", "j": "y", "z": "z", "ʒ": "zh"}
ARPA = dict(zip("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split(),
                "ɑ æ ʌ ɔ aʊ aɪ ɛ ɝ eɪ ɪ i oʊ ɔɪ ʊ u".split()))
ARPA.update(dict(zip("B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH".split(),
                     "b tʃ d ð f ɡ h dʒ k l m n ŋ p ɹ s ʃ t θ v w j z ʒ".split())))
ONSETS = {tuple(x.split()) for x in (
    "p ɹ", "b ɹ", "t ɹ", "d ɹ", "k ɹ", "ɡ ɹ", "f ɹ", "θ ɹ", "ʃ ɹ",
    "p l", "b l", "k l", "ɡ l", "f l", "s l", "s m", "s n", "s p", "s t", "s k",
    "s w", "t w", "d w", "k w", "ɡ w", "θ w", "s p ɹ", "s t ɹ", "s k ɹ",
    "s p l", "s k l", "s k w", "b j", "p j", "f j", "v j", "m j", "k j", "h j")}


def render_respelling(value: str) -> dict:
    guide = " ".join(value.strip().removeprefix("(").removesuffix(")").split())
    if not re.fullmatch(r"[A-Za-z]+(?:[- ][A-Za-z]+)*", guide) or " or " in guide.casefold():
        raise ValueError("Incomplete or unsupported reference respelling")
    if not any(c.isupper() for c in guide):
        raise ValueError("Reference respelling has no stress marker")
    return {"pronunciation": guide, "conversion": [{"respelling": word} for word in guide.split()]}


def from_arpabet(value: str) -> list[list[tuple[str, int]]]:
    word = []
    for token in value.split():
        match = re.fullmatch(r"([A-Z]+)([012]?)", token)
        if not match or match[1] not in ARPA:
            raise ValueError(f"Unsupported ARPABET token: {token}")
        base, stress = match.groups()
        sound = ARPA[base]
        if (sound in VOWELS) != bool(stress):
            raise ValueError(f"Invalid vowel/stress token: {token}")
        if base == "AH" and stress == "0": sound = "ə"
        if base == "ER" and stress == "0": sound = "ɚ"
        word.append((sound, int(stress or 0)))
    return [word]


def from_moby(value: str) -> list[list[tuple[str, int]]]:
    """Decode Grady Ward's documented ASCII phone set; reject unsupported foreign sounds."""
    symbols = {"&": "æ", "(@)": "ɛ", "A": "ɑ", "eI": "eɪ", "@": "ə", "-": "ə",
               "tS": "tʃ", "E": "ɛ", "i": "i", "hw": "hw", "I": "ɪ", "aI": "aɪ",
               "dZ": "dʒ", "N": "ŋ", "Oi": "ɔɪ", "AU": "aʊ", "O": "ɔ", "oU": "oʊ",
               "u": "u", "U": "ʊ", "r": "ɹ", "S": "ʃ", "T": "θ", "D": "ð",
               "@r": "ɚ", "Z": "ʒ", "g": "ɡ"}
    symbols.update({c: c for c in "bdfhklmnps tvwjz".replace(" ", "")})
    words = []
    for part in value.split("_"):
        word, stress, index = [], 0, 0
        while index < len(part):
            char = part[index]
            if char in "',":
                stress = 1 if char == "'" else 2
                index += 1
                continue
            if char == "/":
                end = part.find("/", index + 1)
                if end < 0:
                    raise ValueError("Unterminated Moby phone")
                token, index = part[index + 1:end], end + 1
            else:
                token, index = char, index + 1
            if token not in symbols:
                raise ValueError(f"Unsupported Moby phone: {token}")
            sound = symbols[token]
            if token == "@" and stress:
                sound = "ʌ"
            if token == "@r" and stress:
                sound = "ɝ"
            if sound == "hw":
                word.extend([("h", 0), ("w", 0)])
            else:
                vowel = sound in VOWELS
                word.append((sound, stress if vowel else 0))
                if vowel:
                    stress = 0
        if stress:
            raise ValueError("Stress marker without a vowel")
        words.append(word)
    return words


def from_ipa(value: str) -> list[list[tuple[str, int]]]:
    value = unicodedata.normalize("NFC", value).strip().strip("/[]")
    if value.count("(") != value.count(")"):
        raise ValueError("Unbalanced optional sounds")
    for old, new in (("t͡ʃ", "tʃ"), ("d͡ʒ", "dʒ"), ("ʧ", "tʃ"), ("ʤ", "dʒ"),
                     ("ɜɹ", "ɝ"), ("əɹ", "ɚ"), ("ɫ", "l"), ("ɾ", "t"), ("g", "ɡ"),
                     ("r", "ɹ"), ("ᵊ", "ə"),
                     ("l̩", "əl"), ("n̩", "ən"), ("m̩", "əm")):
        value = value.replace(old, new)
    words = []
    symbols = sorted(VOWELS.keys() | CONSONANTS.keys(), key=len, reverse=True)
    for raw_word in value.split():
        word, stress, index = [], 0, 0
        while index < len(raw_word):
            char = raw_word[index]
            if char in "ˈˌ":
                stress = 1 if char == "ˈ" else 2
                index += 1
                continue
            if char in ".ːˑ()":  # Boundary/length notation; include optional sounds.
                index += 1
                continue
            symbol = next((s for s in symbols if raw_word.startswith(s, index)), None)
            if symbol is None:
                raise ValueError(f"Unsupported IPA sound in {value!r}: {raw_word[index:]!r}")
            vowel = symbol in VOWELS
            word.append((symbol, stress if vowel else 0))
            if vowel: stress = 0
            index += len(symbol)
        if stress:
            raise ValueError("Stress marker without a vowel")
        words.append(word)
    return words


def render(words: list[list[tuple[str, int]]]) -> dict:
    guides, traces = [], []
    for word in words:
        nuclei = [i for i, (sound, _) in enumerate(word) if sound in VOWELS]
        if not nuclei:
            raise ValueError("Word has no vowel")
        if len(nuclei) > 1 and not any(stress == 1 for _, stress in word):
            raise ValueError("Multisyllabic source has no primary stress")
        boundaries = [0]
        for left, right in zip(nuclei, nuclei[1:]):
            cluster = [sound for sound, _ in word[left + 1:right]]
            onset = 0
            for size in range(len(cluster), 0, -1):
                suffix = tuple(cluster[-size:])
                if suffix in ONSETS or (size == 1 and suffix[0] != "ŋ"):
                    onset = size
                    break
            # Close stressed short vowels for readable English guides (SIN-uh,
            # MAS-tee), preserving the identical continuous phone sequence.
            if cluster and word[left][0] in {"æ", "ɛ", "ɪ", "ʊ", "ʌ"} and word[left][1] == 1:
                onset = min(onset, len(cluster) - 1)
            boundaries.append(right - onset)
        boundaries.append(len(word))
        syllables = [word[a:b] for a, b in zip(boundaries, boundaries[1:])]
        if [phone for syllable in syllables for phone in syllable] != word:
            raise ValueError("Syllabification changed the sound sequence")
        parts = []
        for number, syllable in enumerate(syllables):
            pieces = [VOWELS.get(s, CONSONANTS.get(s)) for s, _ in syllable]
            if any(p is None for p in pieces):
                raise ValueError("Unknown sound in renderer")
            for index, ((sound, _), (following, _)) in enumerate(zip(syllable, syllable[1:])):
                if following == "ɹ" and sound in {"ɑ", "ɔ", "ɛ", "ɪ"}:
                    pieces[index] = {"ɑ": "ar", "ɔ": "or", "ɛ": "air", "ɪ": "ir"}[sound]
                    pieces[index + 1] = ""
            text = "".join(pieces)
            primary = any(stress == 1 for _, stress in syllable)
            if primary or (not any(s == 1 for _, s in word) and number == 0):
                text = text.upper()
            parts.append(text)
        guides.append("-".join(parts))
        traces.append({"phones": [p for p, _ in word], "syllablePhones": [[p for p, _ in s] for s in syllables]})
    if not guides:
        raise ValueError("Empty pronunciation")
    guide = " ".join(guides)
    return {"pronunciation": guide, "conversion": traces}
