from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audio.pro_voice_pilot import (
    CSV_FIELDS,
    MANIFEST_FILENAME,
    SCORES_FILENAME,
    PilotError,
    load_spec,
    prepare,
    resolve_terms,
    summarize,
)


class ProVoicePilotTests(unittest.TestCase):
    def test_spec_resolves_six_sessions_and_sixty_unique_terms(self) -> None:
        spec = load_spec()
        terms = resolve_terms(spec)
        self.assertEqual(len(spec["sessions"]), 6)
        self.assertEqual(len(terms), 60)
        self.assertEqual(len({item.term.casefold() for item in terms}), 60)
        self.assertEqual({item.session for item in terms}, set(range(1, 7)))

    def test_prepare_creates_bound_manifest_prompts_and_blank_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "pilot"
            manifest = prepare(output_dir=output_dir)
            self.assertEqual(manifest["termCount"], 60)
            self.assertEqual(manifest["requiredProWins"], 48)
            self.assertFalse(manifest["productionFilesChanged"])
            self.assertTrue((output_dir / MANIFEST_FILENAME).is_file())
            self.assertEqual(len(list(output_dir.glob("session-*-prompt.txt"))), 6)
            with (output_dir / SCORES_FILENAME).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 60)
            self.assertEqual(rows[0]["pro_accuracy"], "")

    def test_prepare_refuses_to_overwrite_review_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "pilot"
            prepare(output_dir=output_dir)
            with self.assertRaises(PilotError):
                prepare(output_dir=output_dir)

    def test_summary_passes_at_exact_threshold_without_serious_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "pilot"
            prepare(output_dir=output_dir)
            self._fill_scores(output_dir / SCORES_FILENAME, pro_wins=48)
            result = summarize(output_dir=output_dir)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["decision"], "eligible-for-speech-api-pilot")
            self.assertFalse(result["productionAudioApproved"])

    def test_summary_fails_below_threshold_or_with_serious_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            below = Path(tmp) / "below"
            prepare(output_dir=below)
            self._fill_scores(below / SCORES_FILENAME, pro_wins=47)
            self.assertEqual(summarize(output_dir=below)["status"], "failed")

            serious = Path(tmp) / "serious"
            prepare(output_dir=serious)
            self._fill_scores(serious / SCORES_FILENAME, pro_wins=60, serious_row=0)
            result = summarize(output_dir=serious)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["proSeriousErrors"], 1)

    def test_summary_rejects_changed_identity_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "pilot"
            prepare(output_dir=output_dir)
            path = output_dir / SCORES_FILENAME
            self._fill_scores(path, pro_wins=60)
            rows = self._read_rows(path)
            rows[0]["term"] = "different term"
            self._write_rows(path, rows)
            with self.assertRaises(PilotError):
                summarize(output_dir=output_dir)

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def _fill_scores(self, path: Path, pro_wins: int, serious_row: int | None = None) -> None:
        rows = self._read_rows(path)
        for index, row in enumerate(rows):
            if index < pro_wins:
                row.update(
                    pro_accuracy="5",
                    pro_naturalness="5",
                    azure_accuracy="4",
                    azure_naturalness="4",
                )
            else:
                row.update(
                    pro_accuracy="4",
                    pro_naturalness="4",
                    azure_accuracy="5",
                    azure_naturalness="5",
                )
            row["pro_serious_error"] = "yes" if index == serious_row else "no"
        self._write_rows(path, rows)


if __name__ == "__main__":
    unittest.main()
