import json
import unittest

from pronounceit.storage import CustomPronunciations, SavedPronunciations, format_saved_entries


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
            }

            first = storage.save_entry(payload)
            second = storage.save_entry(payload)

            self.assertTrue(first.saved)
            self.assertFalse(first.duplicate)
            self.assertFalse(second.saved)
            self.assertTrue(second.duplicate)
            saved = json.loads((tmp_path / "user_files" / "saved_pronunciations.json").read_text())
            self.assertEqual(len(saved), 1)
            self.assertTrue(storage.contains({"term": "Agranulocytosis"}))
            self.assertFalse(storage.contains({"term": "clozapine"}))

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


if __name__ == "__main__":
    unittest.main()
