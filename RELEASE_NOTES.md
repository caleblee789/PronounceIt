# PronounceIt v1.2.0 Release Notes

> Offline pronunciation pack version 2 remains separately published and is not embedded in the add-on archive.

## Summary

PronounceIt v1.2.0 refines reviewer playback, onboarding, and appearance. Plain right-click remains Anki-native, while Control/Ctrl + left- or right-click or selected text opens the quick pronunciation card, and pronunciation is available before answer reveal by default.

## Highlights

- Adds one Option/Alt modifier key: hold it while clicking or selecting text, or press it after selecting, to play pronunciation.
- Adds a separate Ctrl-default quick-card modifier for PronounceIt actions.
- Restores plain right-click to Anki and opens the quick pronunciation card with Control/Ctrl activation.
- Enables pre-answer pronunciation by default while preserving explicit disabled preferences.
- Adds a one-time optional offline-pack prompt and moves all pack controls into the main settings view.
- Replaces the old theme presets with unified Progressbar-style Light and Dark themes across Qt and reviewer surfaces.
- Replaces the text Support control with the image-backed Buy Me a Coffee button.
- Adds anchored loading, success, blocked, and failure feedback without forcing a popup.
- Upgrades Saved Pronunciations with search, Play, Open Original, and Remove actions.
- Records card, note, and deck metadata for new saved pronunciations when Anki exposes it.
- Replaces the multi-key shortcut with a platform-aware, customizable direct playback modifier and keeps a discoverable Tools action.
- Refreshes README, config docs, and release checklist wording for the v1.2.0 workflow.
- Adds a checksum-bound Azure-native method approval and a separately downloadable 95,902-clip pack.
- Unifies playback reporting around Custom audio, High Quality Downloaded Pack, and Standard text-to-speech.
- Keeps offline-pronunciation-pack downloads running after Settings closes, with persistent status, pause/resume, restart-safe partial files, and non-modal completion or failure notices.
- Makes configuration parsing and saved/custom pronunciation storage resilient to malformed data.
- Adds atomic user-data writes, backups, visible data warnings, safer bridge parsing, and keyboard focus improvements.

## Validation

- `python3 -m unittest discover -s tests`
- `python3 scripts/corpus/audit_pronunciations.py`
- `node --check web/pronounceit.js`
- `PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests`
- `python3 scripts/release/build_ankiaddon.py`
- `unzip -l dist/pronounceit.ankiaddon`

Manual Anki smoke testing should follow `RELEASE_CHECKLIST.md` before publishing the tag, GitHub Release, or AnkiWeb upload.
