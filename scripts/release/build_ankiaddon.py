from __future__ import annotations

import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.qa import audit_pronunciations
from pronounceit.audio import aiff_bytes_have_audio, audio_file_has_content, mp3_bytes_have_audio
from pronounceit.dictionary import PronunciationDictionary
from pronounceit.qa import load_checklist


DIST = ROOT / "dist"
OUT = DIST / "pronounceit.ankiaddon"
INCLUDE_DIRS = ["pronounceit", "web", "data", "audio", "user_files"]
INCLUDE_FILES = [
    "__init__.py",
    "config.json",
    "config.md",
    "manifest.json",
    "LICENSE",
    "README.md",
    "PRONUNCIATION_QA.md",
]
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_FILES = {"data/audio_review_ledger.json"}
ALLOWED_USER_FILES = {
    "user_files/README.txt",
    "user_files/custom_pronunciations.sample.json",
}
FORBIDDEN_ARCHIVE_PREFIXES = ("tests/", "scripts/", ".git/", "dist/")
REQUIRED_ARCHIVE_FILES = {
    "__init__.py",
    "config.json",
    "manifest.json",
    "LICENSE",
    "PRONUNCIATION_QA.md",
    "pronounceit/main.py",
    "pronounceit/dictionary.py",
    "pronounceit/tts.py",
    "pronounceit/qa.py",
    "pronounceit/assets/buy_me_a_coffee.png",
    "pronounceit/assets/spin_up_light.svg",
    "pronounceit/assets/spin_down_light.svg",
    "pronounceit/assets/spin_up_dark.svg",
    "pronounceit/assets/spin_down_dark.svg",
    "web/pronounceit.js",
    "web/pronounceit.css",
    "data/medical_pronunciations.json",
    "data/high_yield_checklist.json",
    "data/medical_pronunciation_lexicon_for_codex.txt",
    "user_files/README.txt",
}


def should_include(path: Path) -> bool:
    if path.as_posix() in EXCLUDED_FILES:
        return False
    if any(part.startswith(".") for part in path.parts):
        return False
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.parts and path.parts[0] == "user_files" and path.as_posix() not in ALLOWED_USER_FILES:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.parts and path.parts[0] == "audio" and path.suffix.casefold() in {".aiff", ".mp3"}:
        return audio_file_has_content(ROOT / path)
    return True


def required_audio_files() -> set[str]:
    dictionary = PronunciationDictionary.bundled()
    return {
        str(dictionary.lookup(term).get("audioFile") or "")
        for term in load_checklist()
        if dictionary.lookup(term).get("audioFile")
    }


def validate_release_quality() -> None:
    audit = audit_pronunciations()
    if not audit.passed:
        raise SystemExit(
            "Pronunciation audit failed; refusing to build release archive:\n"
            f"{audit.as_dict()}"
        )
    required = required_audio_files()
    bundled = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "audio").iterdir()
        if path.is_file()
        and path.suffix.casefold() in {".aiff", ".mp3"}
        and audio_file_has_content(path)
    }
    if len(required) != 155 or bundled != required:
        raise SystemExit(
            "Bundled audio set must contain exactly the 155 high-yield clips: "
            f"required={len(required)} bundled={len(bundled)}"
        )


def validate_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        invalid_audio = sorted(
            name
            for name in names
            if name.startswith("audio/") and (
                (name.casefold().endswith(".aiff") and not aiff_bytes_have_audio(archive.read(name)))
                or (name.casefold().endswith(".mp3") and not mp3_bytes_have_audio(archive.read(name)))
            )
        )

    required_audio = required_audio_files()
    archive_audio = {
        name
        for name in names
        if name.startswith("audio/") and name.casefold().endswith((".aiff", ".mp3"))
    }
    missing = sorted((REQUIRED_ARCHIVE_FILES | required_audio) - names)
    extra_audio = sorted(archive_audio - required_audio)
    forbidden = sorted(
        name
        for name in names
        if name.startswith(FORBIDDEN_ARCHIVE_PREFIXES)
        or "__pycache__" in name
        or any(part.startswith(".") for part in Path(name).parts)
    )
    if missing or forbidden or invalid_audio or extra_audio or len(archive_audio) != 155:
        raise SystemExit(
            "Archive validation failed:\n"
            f"missing={missing}\n"
            f"forbidden={forbidden}\n"
            f"invalid_audio={invalid_audio}"
            f"\nextra_audio={extra_audio}"
        )


def main() -> None:
    validate_release_quality()
    DIST.mkdir(exist_ok=True)
    if OUT.exists():
        OUT.unlink()

    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_name in INCLUDE_FILES:
            archive.write(ROOT / file_name, file_name)
        for dir_name in INCLUDE_DIRS:
            for path in sorted((ROOT / dir_name).rglob("*")):
                if path.is_file() and should_include(path.relative_to(ROOT)):
                    archive.write(path, path.relative_to(ROOT).as_posix())

    validate_archive(OUT)
    print(f"Created {OUT}")


if __name__ == "__main__":
    main()
