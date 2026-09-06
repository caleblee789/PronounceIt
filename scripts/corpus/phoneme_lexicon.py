"""Strict shared pronunciation records for readable guides and local synthesis.

ARPABET vowel stress and explicit syllable/word boundaries are the authority.
Neither renderer invents, drops, or re-phonemizes a sound.
"""
from __future__ import annotations

import re
from typing import Any

from pronounceit.dictionary import normalize_term


VOWELS = {
    "AA": ("ɑ", "ah"), "AE": ("æ", "a"), "AH": ("ʌ", "uh"),
    "AO": ("ɔ", "aw"), "AW": ("W", "ow"), "AY": ("I", "y"),
    "EH": ("ɛ", "eh"), "ER": ("ɜɹ", "ur"), "EY": ("A", "ay"),
    "IH": ("ɪ", "ih"), "IY": ("i", "ee"), "OW": ("O", "oh"),
    "OY": ("Y", "oy"), "UH": ("ʊ", "uu"), "UW": ("u", "oo"),
}
CONSONANTS = {
    "B": ("b", "b"), "CH": ("ʧ", "ch"), "D": ("d", "d"),
    "DH": ("ð", "th"), "F": ("f", "f"), "G": ("ɡ", "g"),
    "HH": ("h", "h"), "JH": ("ʤ", "j"), "K": ("k", "k"),
    "L": ("l", "l"), "M": ("m", "m"), "N": ("n", "n"),
    "NG": ("ŋ", "ng"), "P": ("p", "p"), "R": ("ɹ", "r"),
    "S": ("s", "s"), "SH": ("ʃ", "sh"), "T": ("t", "t"),
    "TH": ("θ", "th"), "V": ("v", "v"), "W": ("w", "w"),
    "Y": ("j", "y"), "Z": ("z", "z"), "ZH": ("ʒ", "zh"),
}


class PronunciationError(ValueError):
    pass


def render_syllable(value: str) -> tuple[str, str, int]:
    phones = value.split()
    if not phones:
        raise PronunciationError("Empty syllable")
    sound: list[str] = []
    guide: list[str] = []
    bases: list[str] = []
    stresses: list[int] = []
    for phone in phones:
        match = re.fullmatch(r"([A-Z]+)([012]?)", phone)
        if not match:
            raise PronunciationError(f"Invalid phoneme: {phone}")
        base, stress = match.groups()
        bases.append(base)
        if base in VOWELS and stress:
            k, g = VOWELS[base]
            stresses.append(int(stress))
            if base == "AH" and stress == "0":
                k = "ə"
            if base == "ER" and stress == "0":
                k, g = "əɹ", "er"
            if base == "AY" and len(phones) == 1:
                g = "eye"
            # Kokoro/Misaki places stress immediately before the vowel nucleus.
            k = {"0": "", "1": "ˈ", "2": "ˌ"}[stress] + k
        elif base in CONSONANTS and not stress:
            k, g = CONSONANTS[base]
        else:
            raise PronunciationError(f"Unknown phoneme or invalid stress: {phone}")
        sound.append(k)
        guide.append(g)
    if len(stresses) != 1:
        raise PronunciationError("Each syllable must contain exactly one stressed/unstressed vowel")
    # Familiar rhotic spellings, without changing the underlying sound sequence.
    for index in range(len(bases) - 1):
        if bases[index + 1] == "R" and bases[index] in {"EH", "AO", "AA"}:
            guide[index] = {"EH": "air", "AO": "or", "AA": "ar"}[bases[index]]
            guide[index + 1] = ""
    stress = stresses[0]
    readable = "".join(guide)
    return "".join(sound), readable.upper() if stress == 1 else readable, stress


def render_record(record: dict[str, Any]) -> dict[str, str]:
    words = record.get("words")
    if not isinstance(words, list) or not words:
        raise PronunciationError("Pronunciation must contain words")
    if normalize_term(" ".join(str(w.get("text", "")) for w in words)) != normalize_term(record["term"]):
        raise PronunciationError(f"Word coverage differs from term: {record['term']}")
    sounds, guides = [], []
    for word in words:
        syllables = word.get("syllables")
        if not isinstance(syllables, list) or not syllables:
            raise PronunciationError("Word must contain syllables")
        rendered = [render_syllable(s) for s in syllables]
        if sum(stress == 1 for _, _, stress in rendered) != 1:
            raise PronunciationError(f"Word must have one primary stress: {word['text']}")
        sounds.append("".join(s for s, _, _ in rendered))
        guides.append("-".join(g for _, g, _ in rendered))
    return {
        "phonemes": " ".join(sounds),
        "pronunciation": " ".join(guides),
        "syllables": " ".join(guides).lower(),
    }


def validate_model_input(phonemes: str, vocab: dict[str, int], limit: int = 510) -> None:
    if not phonemes.strip() or len(phonemes) > limit:
        raise PronunciationError("Empty or overlong synthesis input")
    missing = sorted(set(phonemes) - set(vocab))
    if missing:
        raise PronunciationError(f"Model cannot represent these sounds: {missing}")
