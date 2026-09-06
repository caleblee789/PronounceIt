from __future__ import annotations

import sys
import os
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.qa import audit_pronunciations


DIST = ROOT / "dist"
OUT = DIST / "pronounceit.ankiaddon"
INCLUDE_DIRS = ["pronounceit", "web", "data", "user_files", "pronunciation_licenses"]
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
DATA_FILES = {
    "data/audio_pronunciations.json", "data/written_pronunciations.json",
    "data/written-pronunciation-sources.json", "data/audio-pack-release.json",
    "data/written-guide-attribution.md", "data/written-guide-CMUdict-LICENSE.txt",
    "data/written-guide-Moby-NOTICE.txt", "data/written-guide-Misaki-LICENSE.txt",
}
ALLOWED_USER_FILES = {
    "user_files/README.txt",
    "user_files/custom_pronunciations.sample.json",
}
FORBIDDEN_ARCHIVE_PREFIXES = ("tests/", "scripts/", ".git/", "dist/", "quality/", "audio/")
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
    "pronounceit/ui_components.py",
    "pronounceit/settings.py",
    "pronounceit/theme.py",
    "pronounceit/written_guides.py",
    "pronounceit/assets/buy_me_a_coffee.png",
    "pronounceit/assets/spin_up_light.svg",
    "pronounceit/assets/spin_down_light.svg",
    "pronounceit/assets/spin_up_dark.svg",
    "pronounceit/assets/spin_down_dark.svg",
    "web/pronounceit.js",
    "web/pronounceit.css",
    "pronunciation_licenses/ATTRIBUTION.md",
    "pronunciation_licenses/CMUdict-LICENSE",
    "pronunciation_licenses/Misaki-LICENSE",
    "user_files/README.txt",
} | DATA_FILES


def should_include(path: Path) -> bool:
    if path.as_posix().startswith(FORBIDDEN_ARCHIVE_PREFIXES):
        return False
    if any(part.startswith(".") for part in path.parts):
        return False
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.parts and path.parts[0] == "user_files" and path.as_posix() not in ALLOWED_USER_FILES:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.parts and path.parts[0] == "data" and path.as_posix() not in DATA_FILES:
        return False
    return True


def validate_release_quality(root: Path = ROOT) -> None:
    audit = audit_pronunciations(root / "data/audio_pronunciations.json")
    if not audit.passed:
        raise SystemExit(f"Pronunciation audit failed; refusing to build release archive: {audit.as_dict()}")


def validate_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        entries = archive.namelist()
        names = set(entries)
        corrupt = archive.testzip()
    missing = sorted(REQUIRED_ARCHIVE_FILES - names)
    forbidden = sorted(name for name in names if not should_include(Path(name)))
    if missing or forbidden or corrupt or len(names) != len(entries):
        raise SystemExit(f"Archive validation failed: missing={missing}, forbidden={forbidden}, corrupt={corrupt}")


def add_file(archive: zipfile.ZipFile, name: str, root: Path = ROOT) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, (root / name).read_bytes())


def build_archive(root: Path, output: Path) -> None:
    validate_release_quality(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_name in INCLUDE_FILES:
                add_file(archive, file_name, root)
            for dir_name in INCLUDE_DIRS:
                for path in sorted((root / dir_name).rglob("*")):
                    if path.is_file() and should_include(path.relative_to(root)):
                        add_file(archive, path.relative_to(root).as_posix(), root)
        validate_archive(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Build and validate a PronounceIt add-on archive")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    build_archive(ROOT, args.output)
    print(f"Created {args.output}")


if __name__ == "__main__":
    main()
