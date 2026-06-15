# PronounceIt v1.1.0 Release Notes

## Summary

PronounceIt v1.1.0 refines the reviewer flow around fast answer-side audio, a focused quick menu, and saved-pronunciation review. The release keeps the common path lightweight with Option/Alt-left-click audio, moves secondary actions behind Option/Alt-right-click, and adds a more useful saved-word workflow for terms students want to revisit.

## Highlights

- Adds direct Option/Alt-left-click reviewer audio without opening the popup.
- Adds an Option/Alt-right-click quick menu for Play, Save pronunciation, and Support actions.
- Moves Save pronunciation feedback into the quick menu with Saved and Already saved states.
- Upgrades Saved Pronunciations with search, Play, Open Original, and Remove actions.
- Records card, note, and deck metadata for new saved pronunciations when Anki exposes it.
- Adds settings for left-click and right-click modifier behavior.
- Refreshes README, config docs, and release checklist wording for the v1.1.0 workflow.

## Validation

- `python3 -m unittest discover -s tests`
- `python3 scripts/audit_pronunciations.py`
- `node --check web/pronounceit.js`
- `PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests`
- `python3 scripts/build_ankiaddon.py`
- `unzip -l dist/pronounceit.ankiaddon`

Manual Anki smoke testing should follow `RELEASE_CHECKLIST.md` before publishing the tag, GitHub Release, or AnkiWeb upload.
