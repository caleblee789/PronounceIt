import unittest

from pronounceit.config import PronounceItConfig


class ConfigTests(unittest.TestCase):
    def test_question_side_pronunciation_is_enabled_by_default(self) -> None:
        config = PronounceItConfig.from_mapping(None)

        self.assertTrue(config.allow_on_question_side)
        self.assertTrue(config.as_js_payload()["allowOnQuestionSide"])
        self.assertEqual(config.audio_backend, "local_audio_then_tts")
        self.assertEqual(config.audio_pack_cache_mb, 250)
        self.assertEqual(config.hotkey, "")
        self.assertEqual(config.activation_mode, "context_menu")
        self.assertEqual(config.as_js_payload()["activationMode"], "context_menu")
        self.assertEqual(config.direct_click_modifier, "alt")
        self.assertEqual(config.popup_click_modifier, "alt")
        self.assertEqual(config.native_context_menu_modifier, "ctrl")
        self.assertEqual(config.as_js_payload()["directClickModifier"], "alt")
        self.assertEqual(config.as_js_payload()["contextMenuModifier"], "ctrl")
        self.assertTrue(config.as_js_payload()["showNativeContextMenu"])
        self.assertTrue(config.show_native_context_menu)
        self.assertEqual(config.theme, "light")
        self.assertEqual(config.as_js_payload()["theme"], "light")
        self.assertFalse(config.theme_initialized)
        self.assertFalse(config.audio_pack_prompt_seen)

    def test_question_side_pronunciation_can_be_disabled(self) -> None:
        config = PronounceItConfig.from_mapping({"allow_on_question_side": False})

        self.assertFalse(config.allow_on_question_side)
        self.assertFalse(config.as_js_payload()["allowOnQuestionSide"])

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
                "native_context_menu_modifier": "control",
            }
        )

        self.assertEqual(config.direct_click_modifier, "alt")
        self.assertEqual(config.popup_click_modifier, "meta")
        self.assertEqual(config.native_context_menu_modifier, "ctrl")
        self.assertEqual(config.as_config_mapping()["direct_click_modifier"], "alt")
        self.assertEqual(config.as_config_mapping()["popup_click_modifier"], "meta")
        self.assertEqual(config.as_config_mapping()["native_context_menu_modifier"], "ctrl")

        for modifier in ["alt", "shift", "meta", "ctrl", "mod", "disabled"]:
            with self.subTest(modifier=modifier):
                config = PronounceItConfig.from_mapping(
                    {
                        "direct_click_modifier": modifier,
                        "popup_click_modifier": modifier,
                        "native_context_menu_modifier": modifier,
                    }
                )
                self.assertEqual(config.direct_click_modifier, modifier)
                self.assertEqual(config.popup_click_modifier, modifier)
                self.assertEqual(config.native_context_menu_modifier, modifier)

    def test_click_modifiers_fall_back_for_unsupported_values(self) -> None:
        config = PronounceItConfig.from_mapping(
            {
                "direct_click_modifier": "capslock",
                "popup_click_modifier": "space",
                "native_context_menu_modifier": "fn",
            }
        )

        self.assertEqual(config.direct_click_modifier, "alt")
        self.assertEqual(config.popup_click_modifier, "alt")
        self.assertEqual(config.native_context_menu_modifier, "ctrl")

    def test_theme_accepts_light_and_dark_and_maps_legacy_presets(self) -> None:
        for theme in ["light", "dark"]:
            with self.subTest(theme=theme):
                config = PronounceItConfig.from_mapping({"theme": theme})
                self.assertEqual(config.theme, theme)
                self.assertEqual(config.as_js_payload()["theme"], theme)
                self.assertEqual(config.as_config_mapping()["theme"], theme)

        self.assertEqual(PronounceItConfig.from_mapping({"theme": "clinical_light"}).theme, "light")
        self.assertEqual(PronounceItConfig.from_mapping({"theme": "slate"}).theme, "dark")
        self.assertEqual(PronounceItConfig.from_mapping({"theme": "high_contrast"}).theme, "dark")
        self.assertEqual(PronounceItConfig.from_mapping({"theme": "system"}).theme, "light")
        self.assertEqual(PronounceItConfig.from_mapping({"theme": "neon"}).theme, "light")

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

    def test_malformed_numeric_values_fall_back_and_valid_values_are_clamped(self) -> None:
        malformed = PronounceItConfig.from_mapping(
            {"tts_rate": "fast", "tts_volume": "loud"}
        )
        self.assertEqual(malformed.tts_rate, 0)
        self.assertEqual(malformed.tts_volume, 100)

        clamped = PronounceItConfig.from_mapping(
            {"tts_rate": "99", "tts_volume": -4}
        )
        self.assertEqual(clamped.tts_rate, 10)
        self.assertEqual(clamped.tts_volume, 0)
        self.assertEqual(
            PronounceItConfig.from_mapping({"audio_pack_cache_mb": 9999}).audio_pack_cache_mb,
            2000,
        )

    def test_boolean_values_are_coerced_without_truthy_string_surprises(self) -> None:
        config = PronounceItConfig.from_mapping(
            {
                "enabled": "false",
                "auto_close_on_card_change": "0",
                "allow_on_question_side": "yes",
                "show_context_menu": 0,
                "show_save_button": 1,
            }
        )

        self.assertFalse(config.enabled)
        self.assertFalse(config.auto_close_on_card_change)
        self.assertTrue(config.allow_on_question_side)
        self.assertFalse(config.show_context_menu)
        self.assertTrue(config.show_save_button)

        defaults = PronounceItConfig.from_mapping(
            {"enabled": "maybe", "show_save_button": object()}
        )
        self.assertTrue(defaults.enabled)
        self.assertTrue(defaults.show_save_button)

    def test_legacy_hotkey_is_preserved_but_no_longer_defaulted(self) -> None:
        self.assertEqual(
            PronounceItConfig.from_mapping({"hotkey": "Mod+P"}).hotkey,
            "Mod+P",
        )
        self.assertEqual(
            PronounceItConfig.from_mapping({"hotkey": "Mod+Shift+P"}).hotkey,
            "Mod+Shift+P",
        )

    def test_empty_hotkey_disables_shortcut(self) -> None:
        self.assertEqual(PronounceItConfig.from_mapping({"hotkey": ""}).hotkey, "")


if __name__ == "__main__":
    unittest.main()
