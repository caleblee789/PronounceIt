import json
from unittest.mock import patch
import unittest

from pronounceit.storage import (
    CustomPronunciations,
    SavedPronunciations,
    StorageError,
    format_saved_entries,
)


class StorageTests(unittest.TestCase):
    def test_saved_pronunciations_persist_and_deduplicate(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            from pathlib import Path

            tmp_path = Path(tmp)
            storage = SavedPronunciations(tmp_path)
            payload = {
                "term": "Agranulocytosis",
                "requestedText": "agranulocytosis",
                "pronunciation": "uh-gran-yoo-loh-sy-TOH-sis",
                "syllables": "a-gran-u-lo-cy-to-sis",
                "source": "bundled-medical",
                "found": True,
                "cardId": 123,
                "noteId": 456,
                "deckId": 789,
                "deckName": "Medical School",
                "useTextOverride": True,
                "synthesisText": "custom text read aloud",
            }

            first = storage.save_entry(payload)
            second = storage.save_entry(payload)

            self.assertTrue(first.saved)
            self.assertFalse(first.duplicate)
            self.assertFalse(second.saved)
            self.assertTrue(second.duplicate)
            saved = json.loads((tmp_path / "user_files" / "saved_pronunciations.json").read_text())
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["cardId"], 123)
            self.assertEqual(saved[0]["noteId"], 456)
            self.assertEqual(saved[0]["deckId"], 789)
            self.assertEqual(saved[0]["deckName"], "Medical School")
            self.assertTrue(saved[0]["useTextOverride"])
            self.assertEqual(saved[0]["synthesisText"], "custom text read aloud")
            self.assertTrue(storage.contains({"term": "Agranulocytosis"}))
            self.assertFalse(storage.contains({"term": "clozapine"}))

    def test_saved_pronunciations_remove_entry(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            storage = SavedPronunciations(tmp_path)
            storage.save_entry({"term": "Agranulocytosis", "pronunciation": "first"})
            storage.save_entry({"term": "Clozapine", "pronunciation": "second"})

            self.assertTrue(storage.remove_entry("agranulocytosis"))
            self.assertFalse(storage.remove_entry("missing"))

            saved = json.loads((tmp_path / "user_files" / "saved_pronunciations.json").read_text())
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["term"], "Clozapine")

    def test_format_saved_entries_for_viewer(self) -> None:
        text = format_saved_entries(
            [
                {
                    "term": "Agranulocytosis",
                    "pronunciation": "uh-gran-yoo-loh-sy-TOH-sis",
                    "syllables": "a-gran-u-lo-cy-to-sis",
                    "createdAt": "2026-06-09T00:00:00+00:00",
                }
            ]
        )

        self.assertIn("Saved Pronunciations", text)
        self.assertIn("Agranulocytosis", text)
        self.assertIn("uh-gran-yoo-loh-sy-TOH-sis", text)

    def test_custom_pronunciations_upsert_entry(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            storage = CustomPronunciations(Path(tmp))
            first = storage.upsert_entry("clozapine", "KLOH-zuh-peen", "clo-za-pine")
            second = storage.upsert_entry(
                "clozapine",
                "LOCAL-KLOH-zuh-peen",
                "clo-za-pine",
                "local kloh zuh peen",
            )

            self.assertEqual(first["term"], "clozapine")
            self.assertEqual(second["pronunciation"], "LOCAL-KLOH-zuh-peen")
            self.assertEqual(second["speechText"], "local kloh zuh peen")
            data = json.loads((Path(tmp) / "user_files" / "custom_pronunciations.json").read_text())
            self.assertEqual(len(data["terms"]), 1)
            self.assertEqual(data["terms"][0]["speechText"], "local kloh zuh peen")
            data["terms"][0]["speech_text"] = "legacy override"
            storage.path.write_text(json.dumps(data))
            storage.upsert_entry("clozapine", "KLOH-zuh-peen")
            record = storage.load()["terms"][0]
            self.assertNotIn("speechText", record)
            self.assertNotIn("speech_text", record)

    def test_corrupt_saved_json_is_not_overwritten(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "user_files" / "saved_pronunciations.json"
            path.parent.mkdir()
            original = '{"truncated":'
            path.write_text(original, encoding="utf-8")
            storage = SavedPronunciations(Path(tmp))

            with self.assertRaises(StorageError):
                storage.save_entry({"term": "clozapine"})

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertFalse(path.with_suffix(".json.bak").exists())

    def test_corrupt_custom_json_is_not_overwritten(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "user_files" / "custom_pronunciations.json"
            path.parent.mkdir()
            original = "not json"
            path.write_text(original, encoding="utf-8")
            storage = CustomPronunciations(Path(tmp))

            with self.assertRaises(StorageError):
                storage.upsert_entry("clozapine", "KLOH-zuh-peen", "clo-za-pine")

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_mutations_preserve_malformed_and_unknown_records(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved_path = root / "user_files" / "saved_pronunciations.json"
            saved_path.parent.mkdir()
            saved_path.write_text(json.dumps(["keep-me", {"term": "clozapine"}]))
            saved = SavedPronunciations(root)
            saved.save_entry({"term": "Agranulocytosis"})
            saved_raw = json.loads(saved_path.read_text())
            self.assertIn("keep-me", saved_raw)
            self.assertTrue(saved_path.with_suffix(".json.bak").exists())

            custom_path = root / "user_files" / "custom_pronunciations.json"
            custom_path.write_text(
                json.dumps({"schema": 2, "terms": [17, {"term": "incomplete"}]})
            )
            custom = CustomPronunciations(root)
            custom.upsert_entry("clozapine", "KLOH-zuh-peen", "clo-za-pine")
            custom_raw = json.loads(custom_path.read_text())
            self.assertEqual(custom_raw["schema"], 2)
            self.assertIn(17, custom_raw["terms"])
            self.assertIn({"term": "incomplete"}, custom_raw["terms"])

    def test_failed_atomic_replace_leaves_original_and_backup(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = SavedPronunciations(root)
            storage.save_entry({"term": "clozapine"})
            original = storage.path.read_text(encoding="utf-8")

            with patch("pronounceit.storage.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(StorageError):
                    storage.save_entry({"term": "agranulocytosis"})

            self.assertEqual(storage.path.read_text(encoding="utf-8"), original)
            self.assertEqual(
                storage.path.with_suffix(".json.bak").read_text(encoding="utf-8"),
                original,
            )


if __name__ == "__main__":
    unittest.main()
