from __future__ import annotations

import sys
import json
import os
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.qa import audit_pronunciations
from pronounceit.audio import aiff_bytes_have_audio, audio_file_has_content, mp3_bytes_have_audio
from pronounceit.dictionary import PronunciationDictionary
from pronounceit.qa import load_checklist
from pronounceit.audio_pack import file_sha256


DIST = ROOT / "dist"
OUT = DIST / "pronounceit.ankiaddon"
INCLUDE_DIRS = ["pronounceit", "web", "data", "audio", "user_files", "pronunciation_licenses"]
INCLUDE_FILES = [
    "__init__.py",
    "config.json",
    "config.md",
    "manifest.json",
    "LICENSE",
    "README.md",
    "PRONUNCIATION_QA.md",
    "PRONUNCIATION_ASSET_ATTRIBUTION.md",
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
    "PRONUNCIATION_ASSET_ATTRIBUTION.md",
    "pronounceit/__init__.py",
    "pronounceit/audio.py",
    "pronounceit/audio_pack.py",
    "pronounceit/audio_pack_download.py",
    "pronounceit/config.py",
    "pronounceit/storage.py",
    "pronounceit/main.py",
    "pronounceit/dictionary.py",
    "pronounceit/tts.py",
    "pronounceit/qa.py",
    "pronounceit/ui.py",
    "pronounceit/theme.py",
    "pronounceit/written_guides.py",
    "pronounceit/written_phonetics.py",
    "pronounceit/assets/buy_me_a_coffee.png",
    "pronounceit/assets/spin_up_light.svg",
    "pronounceit/assets/spin_down_light.svg",
    "pronounceit/assets/spin_up_dark.svg",
    "pronounceit/assets/spin_down_dark.svg",
    "web/pronounceit.js",
    "web/pronounceit.css",
    "data/medical_pronunciations.json",
    "data/written_pronunciations.json",
    "data/written-guide-corrections.json",
    "data/written-guide-attribution.md",
    "data/written-guide-CMUdict-LICENSE.txt",
    "data/written-guide-Moby-NOTICE.txt",
    "data/written-guide-Misaki-LICENSE.txt",
    "data/written-guide-ai-overrides.json",
    "data/audio-pack-release.json",
    "data/bundled_audio_provenance.json",
    "pronunciation_licenses/ATTRIBUTION.md",
    "pronunciation_licenses/CMUdict-LICENSE",
    "pronunciation_licenses/Misaki-LICENSE",
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
    release = json.loads((ROOT / "data/audio-pack-release.json").read_text(encoding="utf-8"))
    if (release.get("schemaVersion") != 3
            or release.get("dictionarySha256") != file_sha256(ROOT / "data/medical_pronunciations.json")):
        raise SystemExit("The add-on dictionary does not match its version 3 audio release")
    audit = audit_pronunciations()
    if not audit.passed:
        raise SystemExit(
            "Pronunciation audit failed; refusing to build release archive:\n"
            f"{audit.as_dict()}"
        )
    if audit.unavailable_written_pronunciation:
        raise SystemExit("Written pronunciation inventory is incomplete; refusing to build the full package.")
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
        or (name.startswith("user_files/") and name not in ALLOWED_USER_FILES)
        or name in EXCLUDED_FILES
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


def add_file(archive: zipfile.ZipFile, name: str) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, (ROOT / name).read_bytes())


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Build and validate a PronounceIt add-on archive")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    validate_release_quality()
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_name in INCLUDE_FILES:
                add_file(archive, file_name)
            for dir_name in INCLUDE_DIRS:
                for path in sorted((ROOT / dir_name).rglob("*")):
                    if path.is_file() and should_include(path.relative_to(ROOT)):
                        add_file(archive, path.relative_to(ROOT).as_posix())
        validate_archive(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Created {output}")


if __name__ == "__main__":
    main()
