import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.generate_wordlist_pronunciations import (
    GENERATED_SOURCE,
    arpabet_to_pronounceit,
    build_outputs,
    exclusion_reason,
    merge_generated_entries,
)


class FakeGenerator:
    def phones_for(self, term: str) -> list[str]:
        return {
            "abacavir": ["AH0", "B", "AE1", "K", "AH0", "V", "IH2", "R"],
            "unverified": ["AH0", "N", "V", "ER1", "AH0", "F", "AY2", "D"],
            "abc": ["EY1", "B", "IY1", "S", "IY1"],
        }.get(term, ["T", "EH1", "S", "T"])


class EmptyGenerator:
    def phones_for(self, term: str) -> list[str]:
        return []


class WordlistPronunciationPipelineTests(unittest.TestCase):
    def test_filter_excludes_abbreviations_and_formula_like_terms(self) -> None:
        self.assertEqual(exclusion_reason("AAA"), "all-caps-acronym")
        self.assertEqual(exclusion_reason("A.B."), "dotted-abbreviation")
        self.assertEqual(exclusion_reason("3tc"), "formula-or-leading-number")
        self.assertEqual(exclusion_reason("A1c"), "alphanumeric-shorthand")
        self.assertEqual(
            exclusion_reason("1,25-dihydroxycholecalciferol"),
            "formula-or-leading-number",
        )
        self.assertEqual(exclusion_reason("abacavir"), "")
        self.assertEqual(exclusion_reason("Achúcarro's"), "")

    def test_build_outputs_accepts_only_source_verified_entries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "medical_pronunciations.json"
            wordlist_file = root / "wordlist.txt"
            verified_file = root / "verified.json"

            data_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "terms": [
                            {
                                "term": "clozapine",
                                "pronunciation": "KLOH-zuh-peen",
                                "syllables": "clo-za-pine",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            wordlist_file.write_text(
                "\n".join(["AAA", "1,25-dihydroxycholecalciferol", "abacavir", "clozapine", "unverified"]),
                encoding="utf-8",
            )
            verified_file.write_text(
                json.dumps(
                    {
                        "terms": [
                            {
                                "term": "abacavir",
                                "pronunciation": "uh-BAK-uh-veer",
                                "syllables": "a-ba-ca-vir",
                                "source": "source-verified-test",
                                "notes": "Explicit pronunciation evidence.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            accepted, excluded, needs_review = build_outputs(
                wordlist_file,
                data_file,
                verified_file,
            )

            self.assertEqual([item["term"] for item in accepted], ["abacavir"])
            self.assertEqual(accepted[0]["speechText"], "uh bak uh veer")
            self.assertEqual(
                excluded,
                [
                    ("AAA", "all-caps-acronym"),
                    ("1,25-dihydroxycholecalciferol", "formula-or-leading-number"),
                ],
            )
            self.assertEqual(needs_review, [("unverified", "source-verification-needed")])

    def test_build_outputs_can_generate_unverified_entries_when_enabled(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "medical_pronunciations.json"
            wordlist_file = root / "wordlist.txt"

            data_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "terms": [
                            {
                                "term": "clozapine",
                                "pronunciation": "KLOH-zuh-peen",
                                "syllables": "clo-za-pine",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            wordlist_file.write_text(
                "\n".join(["AAA", "1,25-dihydroxycholecalciferol", "abacavir", "clozapine"]),
                encoding="utf-8",
            )

            accepted, excluded, needs_review = build_outputs(
                wordlist_file,
                data_file,
                allow_generated=True,
                generator=FakeGenerator(),
            )

            self.assertEqual([item["term"] for item in accepted], ["abacavir"])
            self.assertEqual(accepted[0]["source"], GENERATED_SOURCE)
            self.assertIn("Machine-generated", accepted[0]["notes"])
            self.assertTrue(accepted[0]["pronunciation"])
            self.assertTrue(accepted[0]["syllables"])
            self.assertEqual(accepted[0]["speechText"], "uh bak uh vihr")
            self.assertNotIn("-", accepted[0]["speechText"])
            self.assertFalse(any(character.isupper() for character in accepted[0]["speechText"]))
            self.assertEqual(
                excluded,
                [
                    ("AAA", "all-caps-acronym"),
                    ("1,25-dihydroxycholecalciferol", "formula-or-leading-number"),
                ],
            )
            self.assertEqual(needs_review, [])

    def test_generated_mode_falls_back_when_g2p_returns_no_phones(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "medical_pronunciations.json"
            wordlist_file = root / "wordlist.txt"

            data_file.write_text(json.dumps({"version": 1, "terms": []}), encoding="utf-8")
            wordlist_file.write_text("tourniquet\n", encoding="utf-8")

            accepted, _excluded, needs_review = build_outputs(
                wordlist_file,
                data_file,
                allow_generated=True,
                generator=EmptyGenerator(),
            )

            self.assertEqual(needs_review, [])
            self.assertEqual(accepted[0]["term"], "tourniquet")
            self.assertEqual(accepted[0]["source"], GENERATED_SOURCE)
            self.assertIn("fallback", accepted[0]["notes"])
            self.assertEqual(accepted[0]["speechText"], "tourniquet")
            self.assertTrue(any(character.isupper() for character in accepted[0]["pronunciation"]))

    def test_arpabet_converter_marks_stressed_syllables(self) -> None:
        self.assertEqual(
            arpabet_to_pronounceit(["AH0", "B", "AE1", "K", "AH0", "V", "IH2", "R"]),
            "uh-BAK-uh-VIHR",
        )

    def test_merge_preserves_existing_entries_and_adds_each_verified_term_once(self) -> None:
        with TemporaryDirectory() as tmp:
            data_file = Path(tmp) / "medical_pronunciations.json"
            data_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "terms": [
                            {
                                "term": "clozapine",
                                "pronunciation": "CURATED-KLOH-zuh-peen",
                                "syllables": "curated",
                                "aliases": ["existing-alias"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = merge_generated_entries(
                data_file,
                [
                    {
                        "term": "abacavir",
                        "pronunciation": "uh-BAK-uh-veer",
                        "syllables": "a-ba-ca-vir",
                        "aliases": ["ABC"],
                        "source": "source-verified-test",
                        "notes": "Explicit pronunciation evidence.",
                    },
                    {
                        "term": "clozapine",
                        "pronunciation": "KLOH-zuh-peen",
                        "syllables": "clo-za-pine",
                        "source": "source-verified-test",
                        "notes": "Should not overwrite curated entry.",
                    },
                    {
                        "term": "ABC",
                        "pronunciation": "ay-bee-SEE",
                        "syllables": "a-b-c",
                        "source": "source-verified-test",
                        "notes": "Alias collision should be skipped.",
                    },
                ],
            )

            data = json.loads(data_file.read_text(encoding="utf-8"))
            terms = {item["term"]: item for item in data["terms"]}
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["skipped"], 2)
            self.assertEqual(terms["clozapine"]["pronunciation"], "CURATED-KLOH-zuh-peen")
            self.assertEqual(terms["abacavir"]["speechText"], "uh bak uh veer")
            self.assertNotIn("ABC", terms)


if __name__ == "__main__":
    unittest.main()
