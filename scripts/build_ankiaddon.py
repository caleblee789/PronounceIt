from __future__ import annotations

import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.qa import audit_pronunciations


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
EXCLUDED_USER_FILES = {
    "user_files/custom_pronunciations.json",
    "user_files/saved_pronunciations.json",
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
    "web/pronounceit.js",
    "web/pronounceit.css",
    "data/medical_pronunciations.json",
    "data/high_yield_checklist.json",
    "data/medical_pronunciation_lexicon_for_codex.txt",
    "user_files/README.txt",
}


def should_include(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.as_posix().startswith("user_files/generated_audio/"):
        return False
    if path.as_posix() in EXCLUDED_USER_FILES:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def validate_release_quality() -> None:
    audit = audit_pronunciations()
    if not audit.passed:
        raise SystemExit(
            "Pronunciation audit failed; refusing to build release archive:\n"
            f"{audit.as_dict()}"
        )


def validate_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

    missing = sorted(REQUIRED_ARCHIVE_FILES - names)
    forbidden = sorted(
        name
        for name in names
        if name.startswith(FORBIDDEN_ARCHIVE_PREFIXES) or "__pycache__" in name
    )
    if missing or forbidden:
        raise SystemExit(
            "Archive validation failed:\n"
            f"missing={missing}\n"
            f"forbidden={forbidden}"
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
