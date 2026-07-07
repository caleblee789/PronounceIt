# PronounceIt v1.1.0 Release Notes

> Audio pack version 2 is the first public pack. Local artifacts are prepared here; publishing the separate pack remains an explicit later step.

## Summary

PronounceIt v1.1.0 refines the reviewer flow around fast answer-side audio, seamless text selection, and saved-pronunciation review. The release makes plain right-click play immediately with details, uses one customizable activation modifier for click, drag, and selected-text playback, and keeps Anki's context menu available with Shift + right-click.

## Highlights

- Adds one Option/Alt activation modifier: hold it while clicking or selecting text, or press it after selecting, to play audio.
- Makes plain right-click play immediately with pronunciation details and Save; Shift + right-click opens Anki's context menu.
- Adds anchored loading, success, blocked, and failure feedback without forcing a popup.
- Upgrades Saved Pronunciations with search, Play, Open Original, and Remove actions.
- Records card, note, and deck metadata for new saved pronunciations when Anki exposes it.
- Replaces the multi-key shortcut with a platform-aware, customizable single modifier and keeps a discoverable Tools action.
- Refreshes README, config docs, and release checklist wording for the v1.1.0 workflow.
- Adds a checksum-bound Azure-native method approval and a separately downloadable 95,902-clip pack.
- Keeps comprehensive-pack downloads running after Settings closes, with persistent progress, pause/resume, restart-safe partial files, and non-modal completion or failure notices.
- Makes configuration parsing and saved/custom pronunciation storage resilient to malformed data.
- Adds atomic user-data writes, backups, visible data warnings, safer bridge parsing, and keyboard focus improvements.

## Validation

- `python3 -m unittest discover -s tests`
- `python3 scripts/audit_pronunciations.py`
- `node --check web/pronounceit.js`
- `PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests`
- `python3 scripts/build_ankiaddon.py`
- `unzip -l dist/pronounceit.ankiaddon`

Manual Anki smoke testing should follow `RELEASE_CHECKLIST.md` before publishing the tag, GitHub Release, or AnkiWeb upload.
