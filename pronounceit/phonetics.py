from __future__ import annotations

import html
import re
from typing import Iterable


PHONE_RE = re.compile(r"^([A-Z]+)([0-2]?)$")
ARPABET_TO_SAPI = {
    "AA": "aa",
    "AE": "ae",
    "AH": "ah",
    "AO": "ao",
    "AW": "aw",
    "AY": "ay",
    "B": "b",
    "CH": "ch",
    "D": "d",
    "DH": "dh",
    "EH": "eh",
    "ER": "er",
    "EY": "ey",
    "F": "f",
    "G": "g",
    "HH": "h",
    "IH": "ih",
    "IY": "iy",
    "JH": "jh",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ng",
    "OW": "ow",
    "OY": "oy",
    "P": "p",
    "R": "r",
    "S": "s",
    "SH": "sh",
    "T": "t",
    "TH": "th",
    "UH": "uh",
    "UW": "uw",
    "V": "v",
    "W": "w",
    "Y": "y",
    "Z": "z",
    "ZH": "zh",
}
VOWELS = {
    "AA",
    "AE",
    "AH",
    "AO",
    "AW",
    "AY",
    "EH",
    "ER",
    "EY",
    "IH",
    "IY",
    "OW",
    "OY",
    "UH",
    "UW",
}


def arpabet_to_sapi(phones: Iterable[str]) -> str:
    syllables: list[list[str]] = []
    pending: list[str] = []
    previous_stress = ""
    for raw_phone in phones:
        match = PHONE_RE.match(str(raw_phone).strip().upper())
        if not match:
            continue
        base, stress = match.groups()
        sapi = ARPABET_TO_SAPI.get(base)
        if sapi is None:
            continue
        if base not in VOWELS:
            pending.append(sapi)
            continue
        if base == "AH" and stress == "0":
            sapi = "ax"
        if syllables and pending and stress == "0" and previous_stress in {"1", "2"}:
            syllables[-1].extend(pending)
            pending = []
        rendered_vowel = f"{sapi} {stress}" if stress in {"1", "2"} else sapi
        syllables.append([*pending, rendered_vowel])
        pending = []
        previous_stress = stress
    if pending:
        if syllables:
            syllables[-1].extend(pending)
        else:
            syllables.append(pending)
    return " - ".join(" ".join(part for part in syllable if part) for syllable in syllables)


def build_ssml(
    term: str,
    phoneme_segments: list[tuple[str, str]],
    voice: str = "en-US-AvaNeural",
    rate: str = "-5%",
) -> str:
    rendered: list[str] = []
    for text, phonemes in phoneme_segments:
        safe_text = html.escape(text, quote=False)
        safe_phones = html.escape(phonemes, quote=True)
        if safe_phones:
            rendered.append(f'<phoneme alphabet="sapi" ph="{safe_phones}">{safe_text}</phoneme>')
        else:
            rendered.append(safe_text)
    body = " ".join(rendered) if rendered else html.escape(term, quote=False)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="en-US">'
        f'<voice name="{html.escape(voice, quote=True)}">'
        f'<prosody rate="{html.escape(rate, quote=True)}">{body}</prosody>'
        "</voice></speak>"
    )
