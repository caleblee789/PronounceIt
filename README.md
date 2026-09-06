# PronounceIt

PronounceIt is an Anki desktop add-on for medical students who want quick pronunciation help while reviewing cards.

Use it before or after revealing an answer:

- Right-click normally for Anki’s standard context menu.
- Hold Option/Alt while clicking or selecting text, or press it after selecting, to play pronunciation without opening details.
- Control/Ctrl + left- or right-click, or select text and press Control/Ctrl to open the quick pronunciation card.

PronounceIt includes 95,902 terms with one readable pronunciation each, 155 bundled high-yield clips, and an optional offline pronunciation pack. Capitals mark stressed sounds. Accepted written pronunciations may differ slightly from the audio. The Azure-native synthesis method is approved against a checksum-bound 1,092-clip pilot; this is method approval, not a claim that every generated clip was individually reviewed.

## Install

Install the built Anki add-on package:

```text
dist/pronounceit.ankiaddon
```

The locally built archive is available at the path above. The offline pronunciation pack is published separately and is never embedded in the add-on archive.

In Anki, open the package through `Tools > Add-ons > Install from file...`, then restart Anki.

## How To Use

1. Start reviewing cards in Anki.
2. Hold Option/Alt while clicking or selecting a medical term, or press it after selecting text, to hear it.
3. Use Control/Ctrl + left- or right-click, or select text and press Control/Ctrl for the quick pronunciation card with Play and Save actions.
4. Use plain right-click for Anki’s standard context menu without PronounceIt actions.

PronounceIt is available before answer reveal by default. You can disable pre-answer pronunciation on the Review tab.

## Saved Pronunciations

Saved words are available from:

```text
Caleb M. Add-ons Settings > PronounceIt settings > Tools > Saved pronunciations
```

The saved list lets you:

- Search saved terms.
- Play a saved pronunciation again.
- Open the original card or note in Anki Browser when available.
- Remove words you no longer need to practice.

Saved pronunciations are stored locally in `user_files/saved_pronunciations.json` and are preserved during add-on upgrades.
Updates are written atomically, with the previous valid file retained as a `.bak` backup. If the JSON is damaged, PronounceIt leaves it unchanged and reports the problem in the UI.

## Tools Menu

PronounceIt adds one item under the shared Tools submenu:

- `Caleb M. Add-ons Settings > PronounceIt settings`: open settings and Advanced tools.

Advanced tools include selected-text playback, pronunciation search, saved pronunciations, custom pronunciation corrections, a pronunciation-library check, playback troubleshooting, local file shortcuts, and support.

## Settings

Open **Caleb M. Add-ons Settings > PronounceIt settings**. The dialog has three tabs:

- **Review:** enable PronounceIt, choose playback and quick-card keys, control before-answer behavior and Save visibility, and select Light or Dark appearance.
- **Audio:** choose recordings with computer-voice fallback, recordings only, or computer voice only. Manage the optional offline pack here; Voice options contains the voice name and speaking speed.
- **Tools:** search, saved pronunciations, custom corrections, library checks, and audio troubleshooting. File shortcuts are under Files.

Search shows a written guide and explicit Play and Save actions in one window. Closing a result does not start playback. The quick card has the same compact actions, a close control, and a Details disclosure for its audio source. Long terms wrap inside the reviewer window.

Audio sources are **Custom audio**, **Recorded audio**, and **Computer voice**. Recordings include bundled clips and the optional offline pack. In recordings-only mode, terms without a recording have a disabled Play action.

### Offline pronunciation pack

The first-run prompt offers an optional background download once. Audio settings shows the current state and relevant actions: Download or Resume, Pause, Cancel download, Update, Check files, and Remove. Downloads continue when Settings closes. Downloaded files stay under `user_files/`, survive add-on updates, and are checked before use.

## Custom Pronunciations

Use `Caleb M. Add-ons Settings > PronounceIt settings > Tools > Add custom pronunciation` for local corrections.

PronounceIt stores custom corrections in:

```text
user_files/custom_pronunciations.json
```

These files stay local to your Anki profile and are preserved during add-on upgrades.

Enter the term and one readable pronunciation in the same editor. Additional options lets you change the text read aloud. Cancel discards the draft; a failed save keeps your input available. Existing custom files with a `syllables` field continue to load, but syllables are no longer displayed separately.

## License

PronounceIt code is released under the MIT License. Written dictionary data has separate attribution and license terms in `data/written-guide-attribution.md`.

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
- `scripts/release/`: add-on build, audio-pack publication, and local pack server scripts.
- `scripts/audio/`: Azure-native audio generation, review, and pack-build scripts.
- `scripts/corpus/`: pronunciation audit and source-lexicon import scripts.
- `tests/`: unit tests.
- `dist/pronounceit.ankiaddon`: built Anki add-on archive.

### Local Testing

1. Open Anki.
2. Go to `Tools > Add-ons > View Files`.
3. Copy or symlink this repository folder into `addons21/pronounceit`.
4. Restart Anki.
5. Review a card and test pre-answer playback, Option/Alt selection gestures, plain right-click, and every Control/Ctrl quick-card gesture.

### Build

```bash
python3 scripts/release/build_ankiaddon.py
```

The archive is written to:

```text
dist/pronounceit.ankiaddon
```

### Validation

Run before distribution:

```bash
python3 -m unittest discover -s tests
python3 scripts/corpus/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests
python3 scripts/release/build_ankiaddon.py
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

- Restores plain right-click to Anki and opens PronounceIt’s quick pronunciation card with Control/Ctrl activation.
- Adds one customizable modifier for click, drag-selection, and selected-text playback.
- Adds a separate Control/Ctrl-default modifier for the quick pronunciation card.
- Enables pronunciation before answer reveal by default.
- Adds one-time offline-pack onboarding and permanently visible pack controls.
- Replaces the old theme presets with neutral Light and Dark themes.
- Replaces the multi-key shortcut with one customizable playback modifier and a discoverable Tools action.
- Upgrades Saved Pronunciations into a searchable dialog with Play, Open Original, and Remove actions.
- Stores card, note, and deck metadata for newly saved pronunciations when Anki provides it.
- Refreshes README and config wording around the quick pronunciation card and saved-word workflow.

See `RELEASE_NOTES.md` for the PR and release summary.

### Corpus Maintenance

The UI shows one readable pronunciation field, with primary stress in capitals. Long phrases may wrap. Written guides use Wiktionary first, CMUdict second, then fully referenced phrase components and documented corrections. US English is preferred; other standard variants are accepted. Written guides do not need to match the audio exactly.

```text
clozapine -> KLOH-zuh-peen
```

Rebuild the text from the pinned local snapshots, then audit it:

```bash
.venv-generation/bin/python scripts/corpus/build_written_guides.py
python3 scripts/corpus/audit_pronunciations.py
```

`data/written_pronunciations.json` records each selected reference or generation method, its phonetics, conversion, and internal status. `build/written-guides/coverage.json` reports coverage and generation counts. Source hashes are verified before building. Dictionary references take priority; remaining terms use US lexicon estimates, medical word-part composition, AI-authored clinical guides, and local US pronunciation rules. These records are marked `AI Generated` internally and have no additional interface label. Full-library linguistic accuracy has not been measured. `data/medical_pronunciations.json` retains legacy audio inputs; the display overlay does not change those inputs or the downloadable pack.

Generation uses the existing `.venv-generation` environment and the packages pinned in `scripts/corpus/requirements-written-guides.txt`. No model or pronunciation-generation dependency is required in Anki. Use `--references-only` with a separate `--output` and `--report` to measure published-reference coverage without filling gaps. AI-authored clinical adjustments live in `data/written-guide-ai-overrides.json`; source-backed corrections live in `data/written-guide-corrections.json`.

The additional reference pass uses NCI's Dictionary of Cancer Terms and the public-domain Moby Pronunciator II. Run `python3 scripts/corpus/fetch_written_sources.py` once to save their checksummed snapshots under `build/written-guide-sources/`. Subsequent builds use those snapshots offline. The rebuild also expects the existing pinned Wiktionary and CMUdict files under `build/kokoro-source-snapshots/`.

Estimate the neural generation job without credentials:

```bash
python3 scripts/audio/generate_neural_audio.py --dry-run
```

Generate the pilot, record the checksum-bound owner approval, and then generate the full corpus. Uncorrected terms use Azure's native pronunciation; only explicit corrections use SAPI phonemes:

```bash
export AZURE_SPEECH_KEY=...
export AZURE_SPEECH_REGION=...
python3 scripts/audio/generate_neural_audio.py --scope high-yield --workers 4
python3 scripts/audio/generate_neural_audio.py --scope curated --workers 4
python3 scripts/audio/generate_neural_audio.py --scope generated-sample --workers 4
python3 scripts/audio/review_audio.py approve-method \
  --reviewer owner \
  --statement "The Azure-native pronunciations sound high quality."
python3 scripts/audio/review_audio.py status

# Reuses pilot clips whose SSML sidecar hash still matches.
python3 scripts/audio/generate_neural_audio.py --scope all --workers 4
python3 scripts/audio/build_audio_pack.py \
  --pack-version 2 \
  --base-url https://github.com/caleblee789/PronounceIt/releases/download/audio-pack-v2 \
  --install-high-yield
```

Azure credentials are read only by the generation script and are never placed in the add-on or audio pack. Any clip is regenerated automatically when its SSML sidecar hash changes.

See `PRONUNCIATION_QA.md` for pronunciation acceptance criteria.
