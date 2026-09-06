import unittest

from pronounceit.theme import DARK, LIGHT, dialog_qss, theme_tokens, web_theme_tokens


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ThemeTests(unittest.TestCase):
    def test_neutral_light_and_dark_palette(self) -> None:
        self.assertEqual((LIGHT.window_bg, LIGHT.card_bg), ("#f5f6f8", "#ffffff"))
        self.assertEqual((DARK.window_bg, DARK.card_bg), ("#1c1f24", "#24282f"))
        self.assertEqual(LIGHT.accent, "#2563eb")
        self.assertEqual(DARK.accent, "#2563eb")

    def test_theme_resolution_has_only_light_and_dark_outputs(self) -> None:
        self.assertIs(theme_tokens("dark"), DARK)
        self.assertIs(theme_tokens("light"), LIGHT)
        self.assertIs(theme_tokens("unexpected"), LIGHT)

    def test_dialog_and_web_tokens_share_semantic_palette(self) -> None:
        for name in ("light", "dark"):
            tokens = theme_tokens(name)
            qss = dialog_qss(name)
            web = web_theme_tokens(name)
            self.assertIn(tokens.window_bg, qss)
            self.assertIn(tokens.card_bg, qss)
            self.assertIn(f"spin_up_{name}.svg", qss)
            self.assertIn(f"spin_down_{name}.svg", qss)
            self.assertEqual(web["bg"], tokens.card_bg)
            self.assertEqual(web["accent"], tokens.accent)
            self.assertEqual(web["status"], tokens.success)

    def test_theme_tokens_keep_text_and_controls_readable(self) -> None:
        for tokens in (LIGHT, DARK):
            with self.subTest(theme=tokens.name):
                for foreground, background in (
                    (tokens.primary_text, tokens.window_bg),
                    (tokens.primary_text, tokens.card_bg),
                    (tokens.secondary_text, tokens.card_bg),
                    (tokens.muted_text, tokens.card_bg),
                    (tokens.button_text, tokens.button_bg),
                    (tokens.disabled_text, tokens.disabled_bg),
                    (tokens.accent_text, tokens.accent),
                    (tokens.success, tokens.card_bg),
                    (tokens.warning, tokens.card_bg),
                    (tokens.danger, tokens.card_bg),
                ):
                    self.assertGreaterEqual(_contrast(foreground, background), 4.5)
                self.assertGreaterEqual(_contrast(tokens.card_border, tokens.card_bg), 3.0)


if __name__ == "__main__":
    unittest.main()
