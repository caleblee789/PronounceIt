# PronounceIt v1.1.0 Release Notes

> Offline pronunciation pack version 2 is the first public pack. Local artifacts are prepared here; publishing the separate pack remains an explicit later step.

## Summary

PronounceIt v1.1.0 refines reviewer playback, onboarding, and appearance. Plain right-click remains Anki-native, while Control/Ctrl + left- or right-click or selected text opens the quick pronunciation card, and pronunciation is available before answer reveal by default.

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
- Refreshes README, config docs, and release checklist wording for the v1.1.0 workflow.
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
# Unreleased — written pronunciation refresh

- Shows one readable pronunciation field throughout quick cards, details, saved entries, and custom corrections.
- Uses Wiktionary as the primary written source, with CMUdict, referenced components, and documented corrections filling gaps.
- Adds an additional gap-filling pass using NCI and Moby reference data.
- Fills remaining terms with generated guides whose methods and `AI Generated` status are stored internally. Results show one pronunciation without a generation label.
- Preserves existing audio inputs and user corrections, and accepts legacy syllable fields without displaying them.
- Adds reproducible source provenance, a coverage report, and dictionary-data attribution.

## Unreleased — UI release polish

- Organizes settings into Review, Audio, and Tools with compact layouts and shared Light/Dark styling.
- Keeps search and results together with explicit playback; replaces custom prompts with one cancellable editor.
- Replaces the saved-word table with a list and retains search, playback, removal, and original-card links.
- Fits quick cards to the reviewer after lookup, status changes, and resizing; wraps long terms and moves audio-source information into Details.
- Preserves block boundaries when selecting card text and keeps inline phrase offsets intact.
- Uses clear audio-source labels and disables unavailable recordings in recordings-only mode.
- Gives errors a short explanation with technical details available separately.
- Preserves the written-guide pipeline, existing configuration keys, and local user data formats.
