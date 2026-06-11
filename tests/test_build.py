import unittest
import zipfile
from tempfile import TemporaryDirectory
from pathlib import Path

from scripts import build_ankiaddon
from scripts.import_source_lexicon import merge_lexicon, parse_source_lexicon, pronunciation_to_speech_text


class BuildScriptTests(unittest.TestCase):
    def test_should_include_rejects_python_cache_files(self) -> None:
        self.assertFalse(build_ankiaddon.should_include(Path("pronounceit/__pycache__/main.pyc")))
        self.assertFalse(build_ankiaddon.should_include(Path("pronounceit/main.pyc")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/generated_audio/example.aiff")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/saved_pronunciations.json")))
        self.assertFalse(build_ankiaddon.should_include(Path("user_files/custom_pronunciations.json")))
        self.assertTrue(build_ankiaddon.should_include(Path("pronounceit/main.py")))
        self.assertTrue(build_ankiaddon.should_include(Path("user_files/custom_pronunciations.sample.json")))
        self.assertIn("audio", build_ankiaddon.INCLUDE_DIRS)

    def test_validate_archive_rejects_forbidden_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "bad.ankiaddon"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for name in build_ankiaddon.REQUIRED_ARCHIVE_FILES:
                    archive.writestr(name, "")
                archive.writestr("tests/test_dictionary.py", "")

            with self.assertRaises(SystemExit):
                build_ankiaddon.validate_archive(archive_path)

    def test_import_source_lexicon_merges_new_and_existing_terms(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_file = tmp_path / "medical_pronunciations.json"
            lexicon_file = tmp_path / "source.txt"
            data_file.write_text(
                """
{
  "version": 1,
  "terms": [
    {"term": "clozapine", "pronunciation": "old", "syllables": "old"}
  ]
}
""".strip(),
                encoding="utf-8",
            )
            lexicon_file.write_text(
                "Header\nclozapine | KLOH-zuh-peen\ntinnitus | TIN-ih-tus or tuh-NY-tus\n",
                encoding="utf-8",
            )

            result = merge_lexicon(data_file, lexicon_file)

            self.assertEqual(result["sourceEntries"], 2)
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["updated"], 1)
            text = data_file.read_text(encoding="utf-8")
            self.assertIn('"pronunciation": "KLOH-zuh-peen"', text)
            self.assertIn('"speechText": "tin ih tus"', text)

    def test_source_lexicon_parser_skips_headers(self) -> None:
        with TemporaryDirectory() as tmp:
            lexicon_file = Path(tmp) / "source.txt"
            lexicon_file.write_text(
                "Format:\nterm | student-friendly pronunciation\nsepsis | SEP-sis\n",
                encoding="utf-8",
            )

            self.assertEqual(parse_source_lexicon(lexicon_file), [("sepsis", "SEP-sis")])

    def test_importer_audio_text_uses_first_alternate(self) -> None:
        self.assertEqual(
            pronunciation_to_speech_text("FEER-koh or VIR-koh"),
            "feer koh",
        )


if __name__ == "__main__":
    unittest.main()
