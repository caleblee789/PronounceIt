# PronounceIt v1.2.1 Release Notes

> Offline pronunciation pack version 2 remains separately published and is not embedded in the add-on archive.

## Summary

PronounceIt v1.2.1 replaces all 95,902 legacy machine-generated pronunciation respellings with independently generated Azure OpenAI gpt-5.6-sol pronunciations. The accompanying syllable and speech-text fields were regenerated from the same Sol output so pronunciation details remain internally consistent.

## Highlights

- Replaces the complete legacy pronunciation corpus with the Sol-generated American English medical pronunciation set.
- Regenerates syllable and speech-text fields for every term instead of retaining stale G2P-derived values.
- Preserves every original term, alias, bundled-audio association, and corpus ordering.
- Marks the new corpus as machine-generated rather than source-verified, so quality provenance remains honest.
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
- Refreshes README and release metadata for the v1.2.1 corpus update.
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
