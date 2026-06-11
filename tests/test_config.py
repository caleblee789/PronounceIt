import unittest

from pronounceit.config import PronounceItConfig


class ConfigTests(unittest.TestCase):
    def test_question_side_pronunciation_is_disabled_by_default(self) -> None:
        config = PronounceItConfig.from_mapping(None)

        self.assertFalse(config.allow_on_question_side)
        self.assertFalse(config.as_js_payload()["allowOnQuestionSide"])
        self.assertEqual(config.audio_backend, "local_audio_then_tts")
        self.assertEqual(config.activation_mode, "context_menu")
        self.assertEqual(config.as_js_payload()["activationMode"], "context_menu")
        self.assertEqual(config.direct_click_modifier, "alt")
        self.assertEqual(config.popup_click_modifier, "alt")
        self.assertEqual(config.as_js_payload()["directClickModifier"], "alt")
        self.assertEqual(config.as_js_payload()["popupClickModifier"], "alt")
        self.assertEqual(config.theme, "system")
        self.assertEqual(config.as_js_payload()["theme"], "system")

    def test_question_side_pronunciation_can_be_enabled(self) -> None:
        config = PronounceItConfig.from_mapping({"allow_on_question_side": True})

        self.assertTrue(config.allow_on_question_side)
        self.assertTrue(config.as_js_payload()["allowOnQuestionSide"])

    def test_activation_mode_accepts_supported_modes_only(self) -> None:
        self.assertEqual(
            PronounceItConfig.from_mapping({"activation_mode": "option_select"}).activation_mode,
            "option_select",
        )
        self.assertEqual(
            PronounceItConfig.from_mapping({"activation_mode": "bad"}).activation_mode,
            "context_menu",
        )

    def test_click_modifiers_accept_supported_values_and_aliases(self) -> None:
        config = PronounceItConfig.from_mapping(
            {
                "direct_click_modifier": "option",
                "popup_click_modifier": "command",
            }
        )

        self.assertEqual(config.direct_click_modifier, "alt")
        self.assertEqual(config.popup_click_modifier, "meta")
        self.assertEqual(config.as_config_mapping()["direct_click_modifier"], "alt")
        self.assertEqual(config.as_config_mapping()["popup_click_modifier"], "meta")

        for modifier in ["alt", "shift", "meta", "ctrl", "mod", "disabled"]:
            with self.subTest(modifier=modifier):
                config = PronounceItConfig.from_mapping(
                    {
                        "direct_click_modifier": modifier,
                        "popup_click_modifier": modifier,
                    }
                )
                self.assertEqual(config.direct_click_modifier, modifier)
                self.assertEqual(config.popup_click_modifier, modifier)

    def test_click_modifiers_fall_back_to_alt_for_unsupported_values(self) -> None:
        config = PronounceItConfig.from_mapping(
            {
                "direct_click_modifier": "capslock",
                "popup_click_modifier": "space",
            }
        )

        self.assertEqual(config.direct_click_modifier, "alt")
        self.assertEqual(config.popup_click_modifier, "alt")

    def test_theme_accepts_supported_presets_only(self) -> None:
        for theme in ["system", "clinical_light", "slate", "high_contrast"]:
            with self.subTest(theme=theme):
                config = PronounceItConfig.from_mapping({"theme": theme})
                self.assertEqual(config.theme, theme)
                self.assertEqual(config.as_js_payload()["theme"], theme)
                self.assertEqual(config.as_config_mapping()["theme"], theme)

        self.assertEqual(
            PronounceItConfig.from_mapping({"theme": "neon"}).theme,
            "system",
        )

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
