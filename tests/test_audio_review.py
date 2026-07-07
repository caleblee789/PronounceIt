import unittest

from pronounceit.audio_review import (
    deterministic_review_sample,
    method_approval_status,
    method_binding_sha256,
    review_status,
    term_categories,
)


class AudioReviewTests(unittest.TestCase):
    def test_method_approval_is_bound_to_all_pilot_inputs(self) -> None:
        binding = {
            "dictionarySha256": "a" * 64,
            "voice": "en-US-AvaNeural",
            "rate": "-5%",
            "outputFormat": "mp3",
            "pilotAssetCount": 1,
            "pilotAssets": [
                {
                    "assetId": "b" * 64,
                    "audioSha256": "c" * 64,
                    "ssmlSha256": "d" * 64,
                }
            ],
        }
        ledger = {
            "methodApproval": {
                "status": "method-approved",
                "scope": "synthesis-method",
                "reviewer": "owner",
                "statement": "The Azure-native pronunciations sound high quality.",
                "binding": binding,
                "bindingSha256": method_binding_sha256(binding),
            }
        }
        self.assertEqual(method_approval_status(ledger, binding), "method-approved")
        changed = {**binding, "rate": "+0%"}
        self.assertEqual(method_approval_status(ledger, changed), "stale")

    def test_review_is_bound_to_current_audio_checksum(self) -> None:
        ledger = {
            "entries": [
                {
                    "assetId": "asset",
                    "audioSha256": "a" * 64,
                    "accuracy": 5,
                    "naturalness": 4,
                    "status": "passed",
                }
            ]
        }
        self.assertEqual(review_status(ledger, "asset", "a" * 64), "passed")
        self.assertEqual(review_status(ledger, "asset", "b" * 64), "unreviewed")

    def test_failed_or_low_scoring_review_does_not_pass(self) -> None:
        ledger = {
            "entries": [
                {
                    "assetId": "asset",
                    "audioSha256": "a" * 64,
                    "accuracy": 3,
                    "naturalness": 5,
                    "status": "passed",
                }
            ]
        }
        self.assertEqual(review_status(ledger, "asset", "a" * 64), "failed")

    def test_deterministic_sample_covers_requested_size_and_categories(self) -> None:
        terms = [f"medicine{i}mab" for i in range(100)]
        terms += [f"pathology{i}itis" for i in range(100)]
        terms += [f"anatomy artery {i}" for i in range(100)]
        terms += [f"bacterium{i}" for i in range(100)]
        terms += [f"longgeneratedmedicalterm{i}" for i in range(300)]
        first = deterministic_review_sample(terms, size=500)
        second = deterministic_review_sample(reversed(terms), size=500)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 500)
        covered = set().union(*(term_categories(term) for term in first))
        self.assertTrue({"drugs", "pathology", "anatomy", "organisms", "multiword"} <= covered)


if __name__ == "__main__":
    unittest.main()
