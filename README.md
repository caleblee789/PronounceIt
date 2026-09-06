# PronounceIt

PronounceIt is an Anki desktop add-on for medical students who want quick pronunciation help while reviewing cards.

Use it before or after revealing an answer:

- Right-click normally for Anki’s standard context menu.
- Hold Option/Alt while clicking or selecting text, or press it after selecting, to play pronunciation without opening details.
- Control/Ctrl + left- or right-click, or select text and press Control/Ctrl to open the quick pronunciation card.

PronounceIt includes a 95,902-term medical pronunciation guide library, 155 bundled high-yield clips, and an optional High Quality Downloaded Pack. The recordings use the owner-approved American English Kokoro voice. Ten pilot clips were accepted; the remaining generated clips have not been individually reviewed.

## Install

Download [PronounceIt v1.3.0](https://github.com/caleblee789/PronounceIt/releases/download/v1.3.0/pronounceit.ankiaddon), then use **Tools > Add-ons > Install from file...** in Anki and restart.

The add-on includes 155 recordings. To get all 95,902, open **Caleb M. Add-ons Settings > PronounceIt settings > Offline pronunciation pack** and choose **Download/Update**. The complete download is approximately **1.03 GiB** and supports pause and resume.

Your custom pronunciations, recordings, and saved words stay in Anki's preserved user files. The new add-on selects the matching version 3 audio pack automatically. The earlier version 2 pack remains available for matching older installations.

The [AnkiWeb listing](https://ankiweb.net/shared/info/1352407063) is a separate distribution channel; this release's verified download is the GitHub package linked above.

## How To Use

1. Start reviewing cards in Anki.
2. Hold Option/Alt while clicking or selecting a medical term, or press it after selecting text, to hear it.
3. Use Control/Ctrl + left- or right-click, or select text and press Control/Ctrl for the quick pronunciation card with Play and Save actions.
4. Use plain right-click for Anki’s standard context menu without PronounceIt actions.

PronounceIt is available before answer reveal by default. You can disable pre-answer pronunciation in Advanced settings.

## Saved Pronunciations

Saved words are available from:

```text
Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Saved pronunciations
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

Open settings from:

```text
Caleb M. Add-ons Settings > PronounceIt settings
```

Common settings include:

- Play pronunciation with: choose the key used to hear a pronunciation directly. It defaults to Option/Alt and can be turned off.
- Open quick card with: choose the key used to open pronunciation details and actions. It defaults to Control/Ctrl and can be turned off.
- Plain right-click opens Anki’s standard menu; Control/Ctrl + left- or right-click, or selected text opens the quick pronunciation card.
- Hold Option/Alt while clicking or selecting text to play pronunciation directly.
- Theme: `Light` or `Dark`, initially chosen from Anki’s current appearance.

Advanced settings include audio choices, pronunciation before the answer is shown, automatic closing of pronunciation cards, Save button visibility, computer voice, speaking speed, volume, and pronunciation tools.

PronounceIt reports three user-facing playback labels: **Custom audio**, **High Quality Downloaded Pack** for all high-quality neural audio, and **Standard text-to-speech** when your computer creates the audio. The selected playback mode determines whether local sources, standard text-to-speech fallback, or both are enabled.

### Offline pronunciation pack

The complete offline-pack controls are always visible in `Caleb M. Add-ons Settings > PronounceIt settings > Offline pronunciation pack`. On first run, users without the pack are offered a one-time background download. The High Quality Downloaded Pack label covers all high-quality neural audio, whether included with the add-on or installed from the full pack. If the pack is unavailable, PronounceIt can use Standard text-to-speech. Downloads continue after Settings closes; reopening Settings reconnects to live status and Download/Update, Pause/Resume, Cancel, Check downloaded files, and Remove pack controls. Pack files live under `user_files/`, survive add-on upgrades, and are checksum-validated before use.

## Custom Pronunciations

Use `Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Add custom pronunciation` for local corrections.

PronounceIt stores custom corrections in:

```text
user_files/custom_pronunciations.json
```

These files stay local to your Anki profile and are preserved during add-on upgrades.

## License

PronounceIt application code is released under the MIT License. The derived pronunciation assets have separate attribution and share-alike terms in `PRONUNCIATION_ASSET_ATTRIBUTION.md` and `pronunciation_licenses/`.

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

GitHub deployment keeps earlier releases intact. Publish the matching version 3 pack, verify the complete anonymous download, and then publish the add-on from the tested source tag. AnkiWeb distribution is tracked separately.

## Release Notes

Version **1.3.0** replaces all 95,902 audio recordings, including the 155 bundled clips, with the accepted local voice and directs downloads to the matching pack. It preserves the written guides from v1.2.1. Pronunciation details now show only Word and Pronunciation. See `RELEASE_NOTES.md` for validation and attribution.

### Corpus Maintenance

PronounceIt favors readable medical-student pronunciations over formal IPA. Stress is marked with capital letters, for example:

```text
agranulocytosis -> uh-GRAN-yoo-loh-sy-TOH-sis
```

When updating the bundled database from the source lexicon, run:

```bash
python3 scripts/corpus/import_source_lexicon.py
python3 scripts/corpus/audit_pronunciations.py
```

The commands below maintain the historical Azure version 2 pipeline. They do not generate or publish the current Kokoro pack. Its source preparation and approval-aware tools are `scripts/corpus/kokoro_sources.py`, `scripts/audio/kokoro_pilot.py`, and `scripts/audio/kokoro_rebuild.py`; original generation inputs and approval evidence are archived with the audio release.

Estimate the historical neural generation job without credentials:

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
