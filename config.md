# PronounceIt Configuration

The settings dialog groups common review choices first and keeps less common controls in Advanced. Anki stores these values in `config.json`.

## Review

- `enabled`: turn the reviewer integration on or off.
- `hotkey`: keyboard shortcut. The default is `Mod+P`, which maps to Ctrl+P on Windows/Linux and Cmd+P on macOS.
- `direct_click_modifier`: modifier for left-click audio-only pronunciation. The default is `alt`.
- `popup_click_modifier`: modifier for right-click quick-menu pronunciation. The default is `alt`.
- Supported click modifiers are `alt`, `shift`, `meta`, `ctrl`, `mod`, and `disabled`.
- `activation_mode` and `show_context_menu`: legacy compatibility keys. New reviewer click behavior is controlled by the click modifier settings above.

## Appearance

- `theme`: default is `system`, which follows the host color preference when possible. Supported presets are `system`, `clinical_light`, `slate`, and `high_contrast`.

## Advanced

- `audio_backend`: audio behavior. The default is `local_audio_then_tts`, which plays bundled pronunciation audio first, generates a cached local clip for unbundled terms, and falls back to system text-to-speech only if local audio is unavailable.
  - `local_audio_then_tts`: use local audio, then system voice if needed.
  - `local_audio`: use local audio only.
  - `system_tts`: use system voice only.
- `allow_on_question_side`: allow lookups before the answer is shown. Defaults to `false`, so PronounceIt only works after flipping the card.
- `auto_close_on_card_change`: close the popup when Anki advances to another card.
- `show_save_button`: show the Save pronunciation action in the quick menu.
- `tts_voice`: optional fallback system voice name. Leave blank for the operating system default.
- `tts_rate`: fallback speech speed from -10 to 10 where supported.
- `tts_volume`: fallback speech volume from 0 to 100 where supported.
- `unknown_term_message`: popup text for terms not found in the bundled dictionary. This remains config-only.
