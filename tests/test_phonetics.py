import unittest

from pronounceit.phonetics import arpabet_to_sapi, build_ssml
from scripts.corpus.phoneme_lexicon import (
    PronunciationError, render_record, validate_model_input,
)
from scripts.corpus.kokoro_sources import arpabet_to_kokoro, ipa_to_kokoro, word_coverage_key


class PhoneticsTests(unittest.TestCase):
    def test_written_conversion_preserves_reference_sounds_and_rejects_unknowns(self) -> None:
        from scripts.corpus.written_phonetics import from_arpabet, from_ipa, from_moby, render, render_respelling
        for words in (from_arpabet("T EH1 S T"), from_ipa("/ˈtɛst/"), from_moby("'t/E/st")):
            guide = render(words)
            self.assertEqual(guide["pronunciation"], "TEHST")
            for trace in guide["conversion"]:
                self.assertEqual(trace["phones"], [p for syllable in trace["syllablePhones"] for p in syllable])
        self.assertEqual(render(from_ipa("/ˈtɛst ˈfɹeɪz/"))["pronunciation"], "TEHST FRAYZ")
        for source in ("/ˈtɛstɬ/", "/tɛstə/", "/tɛ(st/", "/ˈtɛst/ or /tɛst/"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                render(from_ipa(source))
        self.assertEqual(render_respelling("(uh-NEE-mee-uh)")["pronunciation"], "uh-NEE-mee-uh")
        with self.assertRaises(ValueError):
            render_respelling("(... dih-ZEEZ)")

    def test_dictionary_converters_preserve_vowels_stress_and_words(self) -> None:
        vocab = {c: i for i, c in enumerate("tɛsfɹAzˈˌ əʤɜ")}
        self.assertEqual(arpabet_to_kokoro("T EH1 S T", vocab), "tˈɛst")
        self.assertEqual(ipa_to_kokoro("/ˈtɛst ˈfɹeɪz/", vocab), "tˈɛst fɹˈAz")
        for conversion, source in ((arpabet_to_kokoro, "T EH1 BAD"), (ipa_to_kokoro, "/tɛstɬ/")):
            with self.subTest(source=source), self.assertRaises(ValueError):
                conversion(source, vocab)
        self.assertEqual(word_coverage_key("amph(i)-"), word_coverage_key("amph(i)"))
        self.assertNotEqual(word_coverage_key("amph(i)-"), word_coverage_key("amph"))

    def test_shared_record_preserves_sounds_stress_and_word_boundaries(self) -> None:
        result = render_record({
            "term": "test phrase",
            "words": [
                {"text": "test", "syllables": ["T EH1 S T"]},
                {"text": "phrase", "syllables": ["F R EY1 Z"]},
            ],
        })
        self.assertEqual(result["phonemes"], "tˈɛst fɹˈAz")
        self.assertEqual(result["pronunciation"], "TEHST FRAYZ")
        self.assertEqual(result["syllables"], "tehst frayz")

    def test_shared_record_rejects_sound_or_word_loss(self) -> None:
        for syllable in ("T EH1 UNKNOWN", "T EH", "T EH1 AH0"):
            with self.subTest(syllable=syllable), self.assertRaises(PronunciationError):
                render_record({"term": "test", "words": [{"text": "test", "syllables": [syllable]}]})
        with self.assertRaises(PronunciationError):
            render_record({"term": "test phrase", "words": [{"text": "test", "syllables": ["T EH1 S T"]}]})
        with self.assertRaises(PronunciationError):
            validate_model_input("ˈtɛst", {"ˈ": 1, "t": 2, "s": 3})

    def test_arpabet_to_sapi_preserves_stress_and_syllable_boundaries(self) -> None:
        result = arpabet_to_sapi(["AH0", "G", "R", "AE1", "N", "Y", "UW0"])

        self.assertEqual(result, "ax - g r ae 1 n y - uw")

    def test_ssml_wraps_each_word_as_one_phoneme_unit_and_escapes_xml(self) -> None:
        result = build_ssml(
            "A & B",
            [("A", "ey 1"), ("&", ""), ("B", "b iy 1")],
        )

        self.assertIn('<voice name="en-US-AvaNeural">', result)
        self.assertIn('<prosody rate="-5%">', result)
        self.assertIn('<phoneme alphabet="sapi" ph="ey 1">A</phoneme>', result)
        self.assertIn("&amp;", result)


if __name__ == "__main__":
    unittest.main()
