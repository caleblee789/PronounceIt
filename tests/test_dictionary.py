import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pronounceit.dictionary import (
    PronunciationDictionary,
    audio_slug,
    default_audio_file,
    is_plausible_selection,
    lookup_variants,
    normalize_term,
    pronunciation_to_speech_text,
)


class DictionaryTests(unittest.TestCase):
    def test_normalize_term_trims_card_punctuation(self) -> None:
        self.assertEqual(normalize_term("  Agranulocytosis, "), "agranulocytosis")
        self.assertEqual(normalize_term("Crohn disease (CD)"), "crohn disease")
        self.assertEqual(normalize_term("Staphylococcus aureus [MSSA]"), "staphylococcus aureus")

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
