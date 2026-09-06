import unittest
import zipfile
from tempfile import TemporaryDirectory
from pathlib import Path

from scripts.release import build_ankiaddon


class BuildScriptTests(unittest.TestCase):
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
                for name in build_ankiaddon.REQUIRED_ARCHIVE_FILES:
                    archive.writestr(name, "")
                archive.writestr("tests/test_dictionary.py", "")

            with self.assertRaises(SystemExit):
                build_ankiaddon.validate_archive(archive_path)

if __name__ == "__main__":
    unittest.main()
