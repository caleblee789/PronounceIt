import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pronounceit.dictionary import (
    PronunciationDictionary,
    audio_slug,
    default_audio_file,
    display_term,
    is_plausible_selection,
    lookup_variants,
    normalize_term,
    pronunciation_to_speech_text,
)


class DictionaryTests(unittest.TestCase):
    def make_dictionary(self) -> PronunciationDictionary:
        entries = {}
        items = [
            {
                "term": "bundle",
                "pronunciation": "BUN-dul",
                "syllables": "bun-dle",
            },
            {
                "term": "bundle branch block",
                "pronunciation": "BUN-dul branch block",
                "syllables": "bun-dle branch block",
            },
            {
                "term": "right bundle branch block",
                "pronunciation": "RYT BUN-dul branch block",
                "syllables": "right bun-dle branch block",
            },
            {
                "term": "acute lymphoblastic leukemia",
                "pronunciation": "uh-KYOOT lim-foh-BLAS-tik loo-KEE-mee-uh",
                "syllables": "a-cute lym-pho-blas-tic leu-ke-mi-a",
            },
            {
                "term": "focal seizure",
                "pronunciation": "FOH-kul SEE-zhur",
                "syllables": "fo-cal sei-zure",
            },
            {
                "term": "right bundle branch block override",
                "pronunciation": "RYT BUN-dul branch block OH-vur-ryd",
                "syllables": "right bun-dle branch block o-ver-ride",
                "aliases": ["RBBB"],
                "source": "user-override",
            },
            {
                "term": "Wolff-Parkinson-White",
                "pronunciation": "WOOLF PARK-in-sun WYTE",
                "syllables": "wolff par-kin-son white",
            },
        ]
        PronunciationDictionary._merge_entries(entries, items, "test")
        return PronunciationDictionary(entries)

    def test_normalize_term_trims_card_punctuation(self) -> None:
        self.assertEqual(normalize_term("  Agranulocytosis, "), "agranulocytosis")
        self.assertEqual(normalize_term("Crohn disease (CD)"), "crohn disease")
        self.assertEqual(normalize_term("Staphylococcus aureus [MSSA]"), "staphylococcus aureus")

    def test_cloze_markup_is_stripped_before_lookup(self) -> None:
        dictionary = PronunciationDictionary.bundled()

        self.assertEqual(display_term("{{c1::clozapine}}"), "clozapine")
        self.assertEqual(display_term("{{c1::clozapine::antipsychotic}}"), "clozapine")
        self.assertTrue(is_plausible_selection("{{c1::clozapine}}"))
        self.assertTrue(dictionary.lookup("{{c1::clozapine}}")["found"])
        self.assertTrue(dictionary.lookup("{{c1::clozapine::antipsychotic}}")["found"])

    def test_rejects_overbroad_selection(self) -> None:
        self.assertFalse(
            is_plausible_selection("This is a whole sentence with too many words for the popup.")
        )

    def test_core_medical_terms_are_present(self) -> None:
        dictionary = PronunciationDictionary.bundled()
        expected = [
            "agranulocytosis",
            "cholecystokinin",
            "clozapine",
            "pneumothorax",
            "choledocholithiasis",
            "Pseudomonas aeruginosa",
        ]
        missing = [term for term in expected if not dictionary.lookup(term)["found"]]
        self.assertEqual(missing, [])

    def test_lookup_resolves_safe_plural_and_possessive_variants(self) -> None:
        dictionary = PronunciationDictionary.bundled()
        self.assertTrue(dictionary.lookup("carcinomas")["found"])
        self.assertTrue(dictionary.lookup("seizures")["found"])
        self.assertTrue(dictionary.lookup("Crohn's disease")["found"])
        self.assertTrue(dictionary.lookup("Crohn disease (CD)")["found"])
        self.assertTrue(dictionary.lookup("Staphylococcus aureus (MSSA)")["found"])
        self.assertTrue(dictionary.lookup("Wolff\u2011Parkinson\u2011White")["found"])
        self.assertTrue(dictionary.lookup("piperacillin-tazobactam")["found"])
        self.assertTrue(dictionary.lookup("sulfamethoxazole-trimethoprim")["found"])

    def test_lookup_variants_are_conservative(self) -> None:
        self.assertEqual(lookup_variants("carcinomas"), ["carcinomas", "carcinoma"])
        self.assertEqual(lookup_variants("pathologies"), ["pathologies", "pathology"])

    def test_best_context_match_prefers_longest_dictionary_phrase(self) -> None:
        dictionary = self.make_dictionary()
        context = "ECG shows right bundle branch block today."
        start = context.index("bundle")
        leukemia_context = "Concern for acute lymphoblastic leukemia."
        leukemia_start = leukemia_context.index("lymphoblastic")

        self.assertEqual(
            dictionary.best_context_match(context, start, start + len("bundle")),
            "right bundle branch block",
        )
        self.assertEqual(
            dictionary.best_context_match(
                leukemia_context,
                leukemia_start,
                leukemia_start + len("lymphoblastic"),
            ),
            "acute lymphoblastic leukemia",
        )

    def test_best_context_match_prefers_phrase_over_exact_word(self) -> None:
        dictionary = self.make_dictionary()
        context = "ECG shows right bundle branch block today."
        start = context.index("bundle")

        self.assertTrue(dictionary.lookup("bundle")["found"])
        self.assertEqual(
            dictionary.best_context_match(context, start, start + len("bundle")),
            "right bundle branch block",
        )

    def test_best_context_match_falls_back_when_no_phrase_matches(self) -> None:
        dictionary = self.make_dictionary()
        context = "ECG shows unrelated branch wording today."
        start = context.index("branch")

        self.assertEqual(dictionary.best_context_match(context, start, start + len("branch")), "")

    def test_best_context_match_does_not_cross_hard_punctuation(self) -> None:
        dictionary = self.make_dictionary()
        for punctuation in [".", ";", ":", "?", "[", "]", "\n"]:
            with self.subTest(punctuation=punctuation):
                context = f"ECG shows right bundle{punctuation} branch block today."
                start = context.index("branch")

                self.assertEqual(
                    dictionary.best_context_match(context, start, start + len("branch")),
                    "",
                )

    def test_best_context_match_uses_aliases_plurals_and_overrides(self) -> None:
        dictionary = self.make_dictionary()
        plural_context = "History includes focal seizures after fever."
        plural_start = plural_context.index("seizures")
        alias_context = "ECG shows RBBB today."
        alias_start = alias_context.index("RBBB")

        self.assertEqual(
            dictionary.best_context_match(
                plural_context,
                plural_start,
                plural_start + len("seizures"),
            ),
            "focal seizures",
        )
        self.assertEqual(
            dictionary.best_context_match(alias_context, alias_start, alias_start + len("RBBB")),
            "RBBB",
        )

    def test_best_context_match_handles_hyphenated_terms(self) -> None:
        dictionary = self.make_dictionary()
        context = "Possible Wolff\u2011Parkinson\u2011White pattern."
        start = context.index("Parkinson")

        self.assertEqual(
            dictionary.best_context_match(context, start, start + len("Parkinson")),
            "Wolff\u2011Parkinson\u2011White",
        )

    def test_context_fallback_expands_partial_selection_to_whole_tokens(self) -> None:
        dictionary = self.make_dictionary()
        context = "REM sleep improves memory."
        start = context.index("REM") + 1
        end = context.index("sleep") + len("sle")

        self.assertEqual(dictionary.context_fallback_term(context, start, end), "REM sleep")

    def test_context_fallback_does_not_cross_hard_punctuation(self) -> None:
        dictionary = self.make_dictionary()
        context = "REM. sleep improves memory."
        start = context.index("REM") + 1
        end = context.index("sleep") + len("sle")

        self.assertEqual(dictionary.context_fallback_term(context, start, end), "")

    def test_dictionary_has_release_sized_seed_list(self) -> None:
        dictionary = PronunciationDictionary.bundled()
        self.assertGreaterEqual(dictionary.count(), 590)

    def test_pronunciation_entries_have_required_fields(self) -> None:
        dictionary = PronunciationDictionary.bundled()
        data_path = Path(__file__).resolve().parent.parent / "data" / "medical_pronunciations.json"
        self.assertTrue(data_path.exists())
        for term in ["myocardial infarction", "acetaminophen", "meningococcemia"]:
            payload = dictionary.lookup(term)
            self.assertTrue(payload["term"])
            self.assertTrue(payload["pronunciation"])
            self.assertTrue(payload["syllables"])

    def test_user_dictionary_overrides_bundled_entry(self) -> None:
        with TemporaryDirectory() as tmp:
            user_file = Path(tmp) / "custom.json"
            user_file.write_text(
                json.dumps(
                    {
                        "terms": [
                            {
                                "term": "clozapine",
                                "pronunciation": "LOCAL-KLOH-zuh-peen",
                                "syllables": "clo-za-pine",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dictionary = PronunciationDictionary.bundled(user_file=user_file)
            payload = dictionary.lookup("clozapine")
            self.assertEqual(payload["pronunciation"], "LOCAL-KLOH-zuh-peen")
            self.assertEqual(payload["source"], "user-override")
            self.assertEqual(payload["speechText"], "local kloh zuh peen")

    def test_user_dictionary_can_override_speech_text(self) -> None:
        with TemporaryDirectory() as tmp:
            user_file = Path(tmp) / "custom.json"
            user_file.write_text(
                json.dumps(
                    {
                        "terms": [
                            {
                                "term": "clozapine",
                                "pronunciation": "LOCAL-KLOH-zuh-peen",
                                "syllables": "clo-za-pine",
                                "speechText": "custom audio kloh zuh peen",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dictionary = PronunciationDictionary.bundled(user_file=user_file)
            payload = dictionary.lookup("clozapine")
            self.assertEqual(payload["pronunciation"], "LOCAL-KLOH-zuh-peen")
            self.assertEqual(payload["speechText"], "custom audio kloh zuh peen")

    def test_curated_entry_uses_phonetic_audio_text(self) -> None:
        dictionary = PronunciationDictionary.bundled()
        payload = dictionary.lookup("agranulocytosis")
        self.assertEqual(payload["speechText"], "uh gran yoo loh sy toh sis")
        self.assertNotEqual(payload["speechText"], "agranulocytosis")
        self.assertEqual(payload["audioFile"], "audio/agranulocytosis.aiff")

    def test_default_audio_file_slugs_medical_terms(self) -> None:
        self.assertEqual(audio_slug("Wolff-Parkinson-White"), "wolff_parkinson_white")
        self.assertEqual(
            default_audio_file("piperacillin-tazobactam"),
            "audio/piperacillin_tazobactam.aiff",
        )

    def test_high_yield_medical_anchors_are_present(self) -> None:
        dictionary = PronunciationDictionary.bundled()
        expected = [
            "acetazolamide",
            "acyclovir",
            "adalimumab",
            "albuterol",
            "apixaban",
            "cefepime",
            "Clostridioides difficile",
            "Escherichia coli",
            "gastroesophageal reflux disease",
            "Glasgow Coma Scale",
            "GCS",
            "Helicobacter pylori",
            "hypotension",
            "iatrogenic",
            "mydriasis",
            "QRS prolongation",
            "salpingitis",
            "semaglutide",
            "seizures",
            "Staphylococcus aureus",
            "sternocleidomastoid",
            "temporomandibular joint",
            "ureterolithiasis",
            "atrial fibrillation",
            "cellulitis",
            "cirrhosis",
            "pyelonephritis",
            "pulmonary embolism",
            "vulvovaginitis",
            "amphotericin B",
            "Actinomyces",
            "Hashimoto thyroiditis",
            "Wolff-Parkinson-White",
            "thoracentesis",
        ]
        missing = [term for term in expected if not dictionary.lookup(term)["found"]]
        self.assertEqual(missing, [])

    def test_phonetic_text_is_normalized_for_tts(self) -> None:
        self.assertEqual(
            pronunciation_to_speech_text("ghee-YAN bah-RAY SIN-drohm"),
            "ghee yan bah ray sin drohm",
        )

    def test_all_bundled_entries_have_visible_stress_marker(self) -> None:
        import json

        data_path = Path(__file__).resolve().parent.parent / "data" / "medical_pronunciations.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        missing_stress = [
            item["term"]
            for item in data["terms"]
            if not any(character.isupper() for character in item["pronunciation"])
        ]
        self.assertEqual(missing_stress, [])

    def test_all_bundled_entries_have_tts_friendly_speech_text(self) -> None:
        import json

        data_path = Path(__file__).resolve().parent.parent / "data" / "medical_pronunciations.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        dictionary = PronunciationDictionary.bundled()
        bad_terms = []
        for item in data["terms"]:
            payload = dictionary.lookup(item["term"])
            speech_text = payload["speechText"]
            if not speech_text or "-" in speech_text or any(character.isupper() for character in speech_text):
                bad_terms.append(item["term"])
        self.assertEqual(bad_terms, [])


if __name__ == "__main__":
    unittest.main()
