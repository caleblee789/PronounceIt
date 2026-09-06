# PronounceIt Configuration

The settings dialog has Review, Audio, and Tools tabs. Anki stores these values in `config.json`.

## Review

- `enabled`: turn the reviewer integration on or off.
- `direct_click_modifier`: the modifier key. The default is `alt` (Option on macOS): hold it while clicking or selecting text, or press it after selecting, to play pronunciation.
- `hotkey`: legacy compatibility value retained without data loss; multi-key shortcuts are no longer registered. Fresh installs store an empty value.
- `popup_click_modifier`: legacy custom-menu modifier retained so older configurations round-trip without data loss; it no longer controls reviewer behavior.
- `native_context_menu_modifier`: the quick-card modifier. The default is `ctrl` (Control/Ctrl): hold it while left- or right-clicking, or tap it after selecting text, to open the quick pronunciation card.
- Plain right-click opens Anki's normal context menu without PronounceIt actions. Control/Ctrl + left- or right-click, or selected text opens the quick pronunciation card.
- `show_native_context_menu`: enable the quick pronunciation card. The stored key name is retained for compatibility. Defaults to `true`.
- Supported click modifiers are `alt`, `shift`, `meta`, `ctrl`, `mod`, and `disabled`.
- `popup_click_modifier`, `activation_mode`, and `show_context_menu` are retained as legacy compatibility keys. New right-click behavior uses Anki's native context menu.

## Appearance

- `theme`: `light` or `dark`. On first initialization, PronounceIt chooses one from Anki’s current appearance and then keeps the explicit selection. Legacy `clinical_light`, `slate`, `high_contrast`, and `system` values are migrated once.

## Offline pronunciation pack

- The Audio tab shows pack status and only the actions relevant to its current state: Download/Update, Pause/Resume, Cancel download, Check files, and Remove.
- `audio_pack_prompt_seen`: internal one-time onboarding state. Reset to defaults does not clear it.
- `audio_pack_cache_mb`: maximum extracted pack cache size. Defaults to `250` and is clamped to 50–2000 MiB. Downloaded ZIP shards are preserved separately and are not counted against this cache.

## Audio and review behavior

- `audio_backend`: playback mode. The default is `local_audio_then_tts`, which uses Custom audio first, then Recorded audio audio, followed by Computer voice when needed. Recorded audio covers bundled and downloaded recordings.
  - `local_audio_then_tts`: use local audio, then system voice if needed.
  - `local_audio`: use local audio only.
  - `system_tts`: use system voice only.
- `allow_on_question_side`: allow lookups before the answer is shown. Defaults to `true`; an existing explicit `false` remains respected.
- `auto_close_on_card_change`: close the popup when Anki advances to another card.
- `show_save_button`: show Save in search results and quick pronunciation cards.
- `tts_voice`: optional system voice name. Leave blank for the operating system default.
- `tts_rate`: system voice speech rate from -10 to 10 where supported.
- `tts_volume`: system voice volume from 0 to 100 where supported.
- `unknown_term_message`: popup text for terms not found in the bundled dictionary. This remains config-only.
