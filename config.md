# PronounceIt Configuration

- `enabled`: turn the reviewer integration on or off.
- `hotkey`: default is `Mod+P`, which maps to Ctrl+P on Windows/Linux and Cmd+P on macOS.
- `tts_voice`: optional system voice name. Leave blank for the operating system default.
- `tts_rate`: speech rate from -10 to 10 where supported.
- `tts_volume`: speech volume from 0 to 100 where supported.
- `audio_backend`: default is `local_audio_then_tts`, which plays bundled pronunciation audio first, generates a cached local clip for unbundled terms, and falls back to system text-to-speech only if local audio is unavailable. Use `system_tts` to skip bundled/generated audio, or `local_audio` to require local audio without live TTS fallback.
- `show_context_menu`: show the custom right-click "Pronounce selected word" action.
- `show_save_button`: show "Add to pronunciation list" in the pronunciation pop-up.
- `allow_on_question_side`: allow pronunciation lookup before the card answer is revealed. Defaults to `false`, so PronounceIt only works after flipping the card.
