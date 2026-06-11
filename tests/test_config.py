import unittest

from pronounceit.config import PronounceItConfig


class ConfigTests(unittest.TestCase):
    def test_question_side_pronunciation_is_disabled_by_default(self) -> None:
        config = PronounceItConfig.from_mapping(None)

        self.assertFalse(config.allow_on_question_side)
        self.assertFalse(config.as_js_payload()["allowOnQuestionSide"])
        self.assertEqual(config.audio_backend, "local_audio_then_tts")

    def test_question_side_pronunciation_can_be_enabled(self) -> None:
        config = PronounceItConfig.from_mapping({"allow_on_question_side": True})

        self.assertTrue(config.allow_on_question_side)
        self.assertTrue(config.as_js_payload()["allowOnQuestionSide"])

    def test_audio_backend_accepts_supported_modes_only(self) -> None:
        self.assertEqual(
            PronounceItConfig.from_mapping({"audio_backend": "system_tts"}).audio_backend,
            "system_tts",
        )
        self.assertEqual(
            PronounceItConfig.from_mapping({"audio_backend": "local_audio"}).audio_backend,
            "local_audio",
        )
        self.assertEqual(
            PronounceItConfig.from_mapping({"audio_backend": "bad"}).audio_backend,
            "local_audio_then_tts",
        )


if __name__ == "__main__":
    unittest.main()
