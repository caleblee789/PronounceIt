import unittest

from pronounceit.phonetics import arpabet_to_sapi, build_ssml


class PhoneticsTests(unittest.TestCase):
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
