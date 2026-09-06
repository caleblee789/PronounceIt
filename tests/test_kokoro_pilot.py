from __future__ import annotations

import copy
import unittest

from scripts.audio.kokoro_pilot import PilotError, empty_review, load_spec, validate_review
from scripts.corpus.phoneme_lexicon import render_record


class KokoroPilotTests(unittest.TestCase):
    def test_pilot_covers_ten_distinct_canonical_terms_with_shared_pronunciations(self) -> None:
        spec = load_spec()
        self.assertEqual(len({term["term"] for term in spec["terms"]}), 10)
        for term in spec["terms"]:
            with self.subTest(term=term["term"]):
                rendered = render_record(term)
                self.assertTrue(rendered["phonemes"])
                self.assertTrue(rendered["pronunciation"])
                self.assertEqual(rendered["syllables"], rendered["pronunciation"].lower())

    def test_approval_requires_every_term_voice_and_matching_audio_identity(self) -> None:
        manifest = {"bindingSha256": "a" * 64, "entries": [{"assetId": str(i)} for i in range(10)]}
        review = empty_review(manifest)
        self.assertFalse(validate_review(review, manifest)["fullGenerationApproved"])
        for item in review["decisions"]:
            item["decision"] = "accept"
        self.assertFalse(validate_review(review, manifest)["fullGenerationApproved"])
        review["voiceDecision"] = "accept"
        self.assertTrue(validate_review(review, manifest)["fullGenerationApproved"])
        corrected = copy.deepcopy(review)
        corrected["decisions"][0]["decision"] = "needs-correction"
        self.assertFalse(validate_review(corrected, manifest)["fullGenerationApproved"])
        for field in ("binding", "term"):
            altered = copy.deepcopy(review)
            if field == "binding":
                altered["bindingSha256"] = "b" * 64
            else:
                altered["decisions"][0]["assetId"] = "different"
            with self.subTest(field=field), self.assertRaises(PilotError):
                validate_review(altered, manifest)


if __name__ == "__main__":
    unittest.main()
