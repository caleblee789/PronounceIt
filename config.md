# PronounceIt Configuration

The settings dialog groups common review choices first and keeps less common controls in Advanced. Anki stores these values in `config.json`.

## Review

- `enabled`: turn the reviewer integration on or off.
- `direct_click_modifier`: the single activation modifier. The default is `alt` (Option on macOS): hold it while clicking or selecting text, or press it after selecting, to play audio.
- `hotkey`: legacy compatibility value retained without data loss; multi-key shortcuts are no longer registered. Fresh installs store an empty value.
- `popup_click_modifier`: legacy custom-menu modifier retained so older configurations round-trip without data loss; it no longer controls reviewer behavior.
- Plain right-click plays immediately and opens pronunciation details. Shift + right-click opens Anki's context menu.
- `show_native_context_menu`: add PronounceIt Play, Details, and Save actions to the Shift + right-click menu. Defaults to `true`.
- Supported click modifiers are `alt`, `shift`, `meta`, `ctrl`, `mod`, and `disabled`.
- `popup_click_modifier`, `activation_mode`, and `show_context_menu` are retained as legacy compatibility keys. New right-click behavior uses Anki's native context menu.

## Appearance

- `theme`: default is `system`, which follows the host color preference when possible. Supported presets are `system`, `clinical_light`, `slate`, and `high_contrast`.

## Advanced

- `audio_backend`: audio behavior. The default is `local_audio_then_tts`, which plays bundled pronunciation audio first, generates a cached local clip for unbundled terms, and falls back to system text-to-speech only if local audio is unavailable.
  - `local_audio_then_tts`: use local audio, then system voice if needed.
  - `local_audio`: use local audio only.
  - `system_tts`: use system voice only.
- `audio_pack_cache_mb`: maximum extracted comprehensive-pack cache size. Defaults to `250` and is clamped to 50–2000 MiB. Downloaded ZIP shards are preserved separately and are not counted against this cache.
- `allow_on_question_side`: allow lookups before the answer is shown. Defaults to `false`, so PronounceIt only works after flipping the card.
- `auto_close_on_card_change`: close the popup when Anki advances to another card.
- `show_save_button`: show Save pronunciation in both the details popup and native PronounceIt submenu.
- `tts_voice`: optional fallback system voice name. Leave blank for the operating system default.
- `tts_rate`: fallback speech speed from -10 to 10 where supported.
- `tts_volume`: fallback speech volume from 0 to 100 where supported.
- `unknown_term_message`: popup text for terms not found in the bundled dictionary. This remains config-only.
