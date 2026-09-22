import unittest
import json
import zipfile
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Dict, Optional

from scripts.release import build_ankiaddon


class BuildScriptTests(unittest.TestCase):
    @staticmethod
    def _write_valid_archive(
        archive: zipfile.ZipFile,
        manifest: Optional[Dict[str, object]] = None,
    ) -> None:
        for name in build_ankiaddon.expected_archive_files():
            if name == "manifest.json":
                payload = json.dumps(manifest or {"package": "pronounceit", "name": "PronounceIt", "mod": 1})
            elif name == "__init__.py":
                payload = "from .pronounceit.main import initialize\n\ninitialize(__name__)\n"
            else:
                payload = ""
            archive.writestr(name, payload)

    def test_should_include_rejects_python_cache_files(self) -> None:
        self.assertFalse(build_ankiaddon.should_include(Path("pronounceit/__pycache__/main.pyc")))
        self.assertFalse(build_ankiaddon.should_include(Path("pronounceit/main.pyc")))
        self.assertFalse(build_ankiaddon.should_include(Path("web/.DS_Store")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/generated_audio/example.aiff")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/saved_pronunciations.json")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/custom_pronunciations.json")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/saved_pronunciations.json.bak")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/audio/private.aiff")))
        self.assertFalse(build_ankiaddon.should_include(Path("data/audio_review_ledger.json")))
        self.assertTrue(build_ankiaddon.should_include(Path("pronounceit/main.py")))
        self.assertTrue(build_ankiaddon.should_include(Path("user_files/custom_pronunciations.sample.json")))
        self.assertNotIn("audio", build_ankiaddon.INCLUDE_DIRS)
        self.assertFalse(build_ankiaddon.should_include(Path("audio/old.mp3")))
        self.assertFalse(build_ankiaddon.should_include(Path("quality/pronunciation_sources/written.json")))
        self.assertIn("LICENSE", build_ankiaddon.INCLUDE_FILES)
        self.assertIn("LICENSE", build_ankiaddon.REQUIRED_ARCHIVE_FILES)
        self.assertIn(
            "pronounceit/assets/buy_me_a_coffee.png",
            build_ankiaddon.REQUIRED_ARCHIVE_FILES,
        )
        for name in (
            "spin_up_light.svg",
            "spin_down_light.svg",
            "spin_up_dark.svg",
            "spin_down_dark.svg",
        ):
            self.assertIn(
                f"pronounceit/assets/{name}",
                build_ankiaddon.REQUIRED_ARCHIVE_FILES,
            )

    def test_validate_archive_rejects_forbidden_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "bad.ankiaddon"
            with zipfile.ZipFile(archive_path, "w") as archive:
                self._write_valid_archive(archive)
                archive.writestr("tests/test_dictionary.py", "")

            with self.assertRaises(SystemExit):
                build_ankiaddon.validate_archive(archive_path)

    def test_validate_archive_rejects_foreign_addon_module(self) -> None:
        with TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "progress-bar.ankiaddon"
            with zipfile.ZipFile(archive_path, "w") as archive:
                self._write_valid_archive(archive)
                archive.writestr("reviewer_progress_bar.py", "")

            with self.assertRaises(SystemExit):
                build_ankiaddon.validate_archive(archive_path)

    def test_validate_archive_rejects_wrong_identity(self) -> None:
        with TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "wrong-identity.ankiaddon"
            with zipfile.ZipFile(archive_path, "w") as archive:
                self._write_valid_archive(
                    archive,
                    {"package": "progressbar", "name": "Progress Bar"},
                )

            with self.assertRaises(SystemExit):
                build_ankiaddon.validate_archive(archive_path)

if __name__ == "__main__":
    unittest.main()
