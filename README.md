# PronounceIt

PronounceIt is an Anki desktop add-on for medical students who want quick pronunciation help while reviewing cards.

Use it after revealing an answer:

- Option/Alt-left-click a term to play pronunciation audio immediately.
- Option/Alt-right-click a term to open a quick menu with Play and Save pronunciation actions.
- Select text and press `Ctrl+P` on Windows/Linux or `Cmd+P` on macOS.

PronounceIt includes a large bundled medical pronunciation library, so common anatomy, pathology, pharmacology, and clinical terms can play without depending on raw system text-to-speech.

## Install

Install the built Anki add-on package:

```text
dist/pronounceit.ankiaddon
```

In Anki, open the package through `Tools > Add-ons > Install from file...`, then restart Anki.

## How To Use

1. Start reviewing cards in Anki.
2. Reveal the answer.
3. Option/Alt-left-click a medical term to hear it immediately.
4. Option/Alt-right-click a term to open the quick menu.
5. Choose `Play pronunciation` to open the popup and replay the audio.
6. Choose `Save pronunciation` for words that are hard to remember.

PronounceIt is answer-side by default so pronunciation help does not spoil a card before you reveal it.

## Saved Pronunciations

Saved words are available from:

```text
Tools > PronounceIt Settings... > Advanced > Saved List
```

The saved list lets you:

- Search saved terms.
- Play a saved pronunciation again.
- Open the original card or note in Anki Browser when available.
- Remove words you no longer need to practice.

Saved pronunciations are stored locally in `user_files/saved_pronunciations.json` and are preserved during add-on upgrades.

## Tools Menu

PronounceIt adds one Tools menu item:

- `PronounceIt Settings...`: open settings and Advanced tools.

Advanced tools include selected-text pronunciation, manual lookup, saved words, custom pronunciation corrections, dictionary audit, local file shortcuts, and support.

## Settings

Open settings from:

```text
Tools > PronounceIt Settings...
```

Common settings include:

- Keyboard shortcut: defaults to `Mod+P`, which means Ctrl on Windows/Linux and Cmd on macOS.
- Left-click audio modifier: defaults to Option/Alt.
- Right-click quick-menu modifier: defaults to Option/Alt.
- Theme: `system`, `clinical_light`, `slate`, or `high_contrast`.

Advanced settings include audio behavior, pre-answer lookup, popup auto-close, quick-menu Save visibility, fallback voice/speed/volume, utility actions, and shortcuts to local PronounceIt files.

## Custom Pronunciations

Use `Tools > PronounceIt Settings... > Advanced > Custom Pronunciation` for local corrections.

PronounceIt stores custom corrections in:

```text
user_files/custom_pronunciations.json
```

These files stay local to your Anki profile and are preserved during add-on upgrades.

## License

PronounceIt is released under the MIT License. See `LICENSE` for details.

## For Developers

The sections below are for local development, release checks, and pronunciation corpus maintenance.

### Project Layout

- `__init__.py`: Anki add-on entrypoint.
- `manifest.json`: Anki add-on metadata.
- `pronounceit/`: Python add-on code.
- `web/`: reviewer JavaScript and CSS assets.
- `data/medical_pronunciations.json`: bundled pronunciation corpus.
- `audio/`: bundled AIFF audio clips.
- `user_files/`: Anki-preserved local user data.
- `scripts/`: build, audit, import, generation, and corpus maintenance scripts.
- `tests/`: unit tests.
- `dist/pronounceit.ankiaddon`: built Anki add-on archive.

### Local Testing

1. Open Anki.
2. Go to `Tools > Add-ons > View Files`.
3. Copy or symlink this repository folder into `addons21/pronounceit`.
4. Restart Anki.
5. Review a card, reveal the answer, and test Option/Alt-left-click plus Option/Alt-right-click.

### Build

```bash
python3 scripts/build_ankiaddon.py
```

The archive is written to:

```text
dist/pronounceit.ankiaddon
```

### Validation

Run before distribution:

```bash
python3 -m unittest discover -s tests
python3 scripts/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests
python3 scripts/build_ankiaddon.py
unzip -l dist/pronounceit.ankiaddon
```

See `RELEASE_CHECKLIST.md` for the full release gate and manual Anki smoke test.

## Release Notes

Prepared release tag:

```text
v1.1.0
```

Release focus:

- Adds a lightweight Support action in the quick menu and settings dialog.
- Keeps answer-side Option/Alt-left-click audio fast and turns Option/Alt-right-click into a focused quick menu.
- Moves Save pronunciation into the quick menu, with immediate Saved/Already saved feedback.
- Upgrades Saved Pronunciations into a searchable dialog with Play, Open Original, and Remove actions.
- Stores card, note, and deck metadata for newly saved pronunciations when Anki provides it.
- Refreshes README and config wording around the quick menu and saved-word workflow.

### Corpus Maintenance

PronounceIt favors readable medical-student pronunciations over formal IPA. Stress is marked with capital letters, for example:

```text
agranulocytosis -> uh-GRAN-yoo-loh-sy-TOH-sis
```

When updating the bundled database from the source lexicon, run:

```bash
python3 scripts/import_source_lexicon.py
```

To expand from a larger word list, install generation-only dependencies and run:

```bash
python3 -m pip install -r requirements-generation.txt
python3 scripts/generate_wordlist_pronunciations.py \
  --wordlist-file /path/to/wordlist.txt \
  --allow-generated \
  --merge
python3 scripts/generate_bundled_audio.py
python3 scripts/audit_pronunciations.py
```

After changing `data/medical_pronunciations.json`, regenerate bundled clips:

```bash
python3 scripts/generate_bundled_audio.py --force
```

See `PRONUNCIATION_QA.md` for pronunciation acceptance criteria.
