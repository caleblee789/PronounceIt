# PronounceIt

PronounceIt is an Anki desktop add-on for medical students who want quick pronunciation help while reviewing cards.

Use it after revealing an answer:

- Right-click a term to play immediately and open pronunciation details.
- Hold Option/Alt while clicking or selecting text, or press it after selecting, to play audio without opening details.
- Shift + right-click to open Anki's context menu and the native `PronounceIt` submenu.

PronounceIt includes a 95,902-term medical pronunciation guide library, 155 bundled high-yield clips, and an optional comprehensive neural audio pack. The Azure-native synthesis method is approved against a checksum-bound 1,092-clip pilot; this is method approval, not a claim that every generated clip was individually reviewed.

## Install

Install the built Anki add-on package:

```text
dist/pronounceit.ankiaddon
```

The locally built archive is available at the path above. The comprehensive pack is published separately and is never embedded in the add-on archive.

In Anki, open the package through `Tools > Add-ons > Install from file...`, then restart Anki.

## How To Use

1. Start reviewing cards in Anki.
2. Reveal the answer.
3. Right-click a medical term to hear it immediately and view pronunciation details.
4. Alternatively, hold Option/Alt while clicking or selecting text, or press it after selecting.
5. Use Shift + right-click when you need Anki's context menu or the native `PronounceIt` submenu.

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
Updates are written atomically, with the previous valid file retained as a `.bak` backup. If the JSON is damaged, PronounceIt leaves it unchanged and reports the problem in the UI.

## Tools Menu

PronounceIt adds three Tools menu items:

- `Pronounce Word or Selection`: play selected text or the last word under the pointer.
- `PronounceIt Settings...`: open settings and Advanced tools.
- `PronounceIt Audio Diagnostics...`: inspect recent playback attempts, backend failures, and data-loading warnings.

Advanced tools include selected-text pronunciation, manual lookup, saved words, custom pronunciation corrections, dictionary audit, audio diagnostics, local file shortcuts, and support.

## Settings

Open settings from:

```text
Tools > PronounceIt Settings...
```

Common settings include:

- Activation modifier: defaults to Option/Alt and can be changed or disabled.
- Default: Right-click, or hold Option/Alt while selecting text (or press it after selecting), to play audio. Shift + right-click opens Anki’s context menu.
- Native PronounceIt actions remain available inside the Shift + right-click menu.
- Theme: `system`, `clinical_light`, `slate`, or `high_contrast`.

Advanced settings include audio behavior, pre-answer lookup, popup auto-close, native-menu Save visibility, fallback voice/speed/volume, utility actions, and shortcuts to local PronounceIt files.

### Comprehensive Audio Pack

Open `Tools > PronounceIt Settings... > Advanced > Audio` and choose `Download` to install the separately versioned comprehensive pack. Downloads never start without this explicit action. Downloading continues in the background after Settings closes, so Anki remains available for normal review; reopening Settings reconnects to live progress and pause/resume controls. Pack shards and extracted cache files live under `user_files/`, survive add-on upgrades, and are checksum-validated before use.

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
- `audio/`: bundled high-yield AIFF or MP3 audio clips.
- `user_files/`: Anki-preserved local user data.
- `scripts/`: build, audit, import, generation, and corpus maintenance scripts.
- `tests/`: unit tests.
- `dist/pronounceit.ankiaddon`: built Anki add-on archive.

### Local Testing

1. Open Anki.
2. Go to `Tools > Add-ons > View Files`.
3. Copy or symlink this repository folder into `addons21/pronounceit`.
4. Restart Anki.
5. Review a card, reveal the answer, and test right-click playback, Option/Alt selection gestures, and the Shift + right-click menu.

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

GitHub deployment is intentionally staged: publish the immutable `audio-pack-v2`
release only after isolated Anki validation, test the anonymous live download, and
then publish the `v1.1.0` add-on release. AnkiWeb publication is deferred.

## Release Notes

Prepared release tag:

```text
v1.1.0
```

Release focus:

- Makes plain right-click play immediately with pronunciation details and Save.
- Adds one customizable modifier for click, drag-selection, and selected-text playback.
- Keeps Anki's context menu and native PronounceIt actions available through Shift + right-click.
- Replaces the multi-key shortcut with one customizable activation modifier and a discoverable Tools action.
- Upgrades Saved Pronunciations into a searchable dialog with Play, Open Original, and Remove actions.
- Stores card, note, and deck metadata for newly saved pronunciations when Anki provides it.
- Refreshes README and config wording around the native-menu and saved-word workflow.

See `RELEASE_NOTES.md` for the PR and release summary.

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
python3 scripts/audit_pronunciations.py
```

Estimate the neural generation job without credentials:

```bash
python3 scripts/generate_neural_audio.py --dry-run
```

Generate the pilot, record the checksum-bound owner approval, and then generate the full corpus. Uncorrected terms use Azure's native pronunciation; only explicit corrections use SAPI phonemes:

```bash
export AZURE_SPEECH_KEY=...
export AZURE_SPEECH_REGION=...
python3 scripts/generate_neural_audio.py --scope high-yield --workers 4
python3 scripts/generate_neural_audio.py --scope curated --workers 4
python3 scripts/generate_neural_audio.py --scope generated-sample --workers 4
python3 scripts/review_audio.py approve-method \
  --reviewer owner \
  --statement "The Azure-native pronunciations sound high quality."
python3 scripts/review_audio.py status

# Reuses pilot clips whose SSML sidecar hash still matches.
python3 scripts/generate_neural_audio.py --scope all --workers 4
python3 scripts/build_audio_pack.py \
  --pack-version 2 \
  --base-url https://github.com/caleblee789/PronounceIt/releases/download/audio-pack-v2 \
  --install-high-yield
```

Azure credentials are read only by the generation script and are never placed in the add-on or audio pack. Any clip is regenerated automatically when its SSML sidecar hash changes.

See `PRONUNCIATION_QA.md` for pronunciation acceptance criteria.
