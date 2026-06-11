# PronounceIt

PronounceIt is an Anki desktop add-on for medical students who want fast, answer-side pronunciation help while reviewing cards. Option/Alt-left-click a word to play pronunciation audio immediately, Option/Alt-right-click to open a compact reviewer pop-up, or select text and press `Ctrl+P` / `Cmd+P`.

The add-on is designed for review flow: quick to invoke, quiet when the answer is still hidden, and backed by a large bundled pronunciation corpus so common medical, pharmacology, anatomy, pathology, and clinical terms can play without relying on raw system text-to-speech.

## Highlights

- Reviewer-first lookup for selected words and short phrases.
- Answer-side lookup by default, with an option to allow question-side lookup.
- `Ctrl+P` / `Cmd+P` hotkey using Anki's `Mod+P` convention.
- AMBOSS-style floating pop-up anchored near the selected text.
- Option/Alt-left-click audio-only pronunciation.
- Option/Alt-right-click pop-up with autoplay, Play, and save actions.
- Tools > PronounceIt menu for manual lookup, saved words, custom corrections, dictionary audit, and configuration.
- Bundled medical dictionary with about 95,900 unique runtime terms.
- About 95,600 bundled AIFF clips generated from pronunciation-friendly speech text.
- Local audio first, generated local audio second, and system TTS only as fallback by default.
- Custom pronunciation overrides through `user_files/custom_pronunciations.json`.
- Saved pronunciation list in `user_files/saved_pronunciations.json`, preserved by Anki during add-on upgrades.
- Release audit that checks dictionary coverage, high-yield terms, source lexicon consistency, speech text safety, stress markers, and bundled audio.

## How It Works

PronounceIt injects a small JavaScript and CSS reviewer integration into Anki webviews. When review is enabled, it watches for selected text and sends pronunciation requests back to the Python add-on. The Python side normalizes the selection, looks it up in the bundled dictionary plus any user overrides, and returns a payload for the pop-up.

The bundled dictionary uses student-friendly phonetics rather than IPA. Stressed syllables are capitalized, for example:

```text
agranulocytosis -> uh-gran-yoo-loh-sy-TOH-sis
```

Audio is intentionally spoken from normalized pronunciation text instead of the raw medical spelling. This helps avoid common system-TTS misreadings of medical terms.

## Reviewer Usage

1. Review a card in Anki.
2. Reveal the answer.
3. Option/Alt-left-click a term, such as `agranulocytosis`, to play audio only.
4. Option/Alt-right-click a term to open the pop-up and play audio.
5. Use the pop-up Play button to replay the audio.
6. Use the save button to add useful terms to the local saved pronunciation list.

You can also select text and press `Ctrl+P` on Windows/Linux or `Cmd+P` on macOS, or use Tools > PronounceIt > Pronounce Current Selection.

## Tools Menu

PronounceIt adds a grouped Tools > PronounceIt submenu:

- Pronounce Current Selection: pronounces selected reviewer text.
- Pronounce Manually: opens a dialog for terms that are hard to select or when another add-on intercepts selection behavior.
- Saved Pronunciations: shows locally saved words.
- Add or Update Custom Pronunciation: writes local pronunciation corrections.
- Dictionary Audit: runs the bundled quality audit from inside Anki.
- Configure Add-on: opens the settings dialog.

## Configuration

Anki stores the add-on config from `config.json`. The same options are documented in `config.md`.

The settings dialog keeps common review choices on the main screen and places less common controls under Advanced.

Main settings:

- Keyboard shortcut: defaults to `Mod+P`, which maps to Ctrl on Windows/Linux and Cmd on macOS.
- Left-click audio key and right-click popup key: both default to Option/Alt and can be customized separately.
- Audio behavior: defaults to local audio first, with system voice only as a fallback.
- Theme: defaults to `system`; supported presets are `system`, `clinical_light`, `slate`, and `high_contrast`.

Advanced settings include pre-answer lookup, popup auto-close, Save button visibility, fallback voice/speed/volume, and shortcuts to local PronounceIt files. The dictionary audit remains available from Tools > PronounceIt > Dictionary Audit.

The main settings write click modifier keys for the reviewer controls:

- `direct_click_modifier`: controls audio-only left-click pronunciation.
- `popup_click_modifier`: controls right-click popup pronunciation.
- `activation_mode` and `show_context_menu`: retained for compatibility with older configs.
- `audio_backend`: accepts `local_audio_then_tts`, `local_audio`, or `system_tts`.
- `allow_on_question_side`, `show_save_button`, `auto_close_on_card_change`, `tts_voice`, `tts_rate`, `tts_volume`, and `unknown_term_message`: continue to work from `config.json`.

## Local User Files

Anki preserves the `user_files/` directory when an add-on is upgraded.

- `user_files/saved_pronunciations.json`: terms saved from the reviewer pop-up.
- `user_files/custom_pronunciations.sample.json`: copy this to `custom_pronunciations.json` to create local overrides by hand.
- `user_files/custom_pronunciations.json`: local pronunciation corrections, excluded from release archives.
- `user_files/generated_audio/`: cached fallback audio for unbundled terms, excluded from release archives.

A custom pronunciation entry can include:

```json
{
  "term": "example term",
  "pronunciation": "eg-ZAM-pul term",
  "syllables": "eg-zam-pul term",
  "speechText": "eg zam pul term",
  "audioFile": "audio/example_term.aiff"
}
```

`speechText` is optional, but useful when the displayed guide is clear for students and the system voice needs a different prompt.

## Project Layout

- `__init__.py`: Anki add-on entrypoint.
- `manifest.json`: Anki add-on metadata.
- `pronounceit/`: Python add-on code.
- `web/`: reviewer JavaScript and CSS assets.
- `data/medical_pronunciations.json`: bundled pronunciation corpus.
- `data/high_yield_checklist.json`: release-gated high-yield term checklist.
- `data/medical_pronunciation_lexicon_for_codex.txt`: source lexicon used for curated QA.
- `audio/`: bundled AIFF audio clips.
- `user_files/`: Anki-preserved local user data.
- `scripts/`: build, audit, import, generation, and corpus maintenance scripts.
- `tests/`: unit tests for dictionary, config, TTS, storage, web assets, QA, and build behavior.
- `dist/pronounceit.ankiaddon`: built Anki add-on archive.

## Install For Local Testing

1. Open Anki.
2. Go to Tools > Add-ons > View Files.
3. Copy or symlink this repository folder into `addons21/pronounceit`.
4. Restart Anki.
5. Review a card, reveal the answer, and Option/Alt-left-click a medical term to hear it.
6. Option/Alt-right-click the same term to confirm the reviewer popup opens and plays audio.

## Build A Release Archive

Run:

```bash
python3 scripts/build_ankiaddon.py
```

The script writes:

```text
dist/pronounceit.ankiaddon
```

The archive places add-on files at the zip root, as AnkiWeb expects. The build refuses to produce a release archive if the pronunciation audit fails or forbidden development files are present in the archive.

## Validation

Run the release checks before distribution:

```bash
python3 -m unittest discover -s tests
python3 scripts/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests
python3 scripts/build_ankiaddon.py
unzip -l dist/pronounceit.ankiaddon
```

The release audit currently expects:

- About 95,900 runtime dictionary terms.
- 155 high-yield checklist terms with no missing entries.
- 462 source lexicon terms with no missing runtime entries or pronunciation mismatches.
- Display pronunciation, syllables, stress capitalization, safe speech text, and a non-empty bundled audio file for every bundled entry.

See `RELEASE_CHECKLIST.md` for the full gate and manual Anki smoke test.

## Corpus Maintenance

When updating the bundled database from the source lexicon, run:

```bash
python3 scripts/import_source_lexicon.py
```

To expand from a large word list with generated G2P pronunciations, install the generation-only dependency and run:

```bash
python3 -m pip install -r requirements-generation.txt
python3 scripts/generate_wordlist_pronunciations.py \
  --wordlist-file /path/to/wordlist.txt \
  --allow-generated \
  --merge
python3 scripts/generate_bundled_audio.py
python3 scripts/audit_pronunciations.py
```

The word-list pipeline excludes abbreviations and formula-like entries, skips already bundled terms, labels machine-generated entries as `generated-g2p-en`, and writes accepted, excluded, and needs-review reports under `data/`. `g2p-en` may download NLTK assets during first use.

After changing `data/medical_pronunciations.json`, regenerate bundled clips:

```bash
python3 scripts/generate_bundled_audio.py --force
```

Then run the full validation gate.

## Pronunciation QA

PronounceIt favors readable medical-student guidance over formal IPA. Terms in `data/medical_pronunciations.json` are product data and should be reviewed before release expansions.

Quality rules:

- Prefer common US medical-school usage when pronunciation varies regionally.
- Keep display pronunciations readable and stress-marked with capital letters.
- Keep `speechText` lowercase, space-separated, hyphen-free, and free of alternate-pronunciation wording such as `or`.
- Include aliases for abbreviations, alternate spellings, and plural forms that automatic fallback will not catch.
- Add broadly useful new terms to `data/high_yield_checklist.json` when they represent common medical-school review content.
- Promote local corrections into the bundled corpus when they are useful beyond one user's deck.

See `PRONUNCIATION_QA.md` for the detailed acceptance criteria.

## Release Notes

This repository currently includes the built archive at `dist/pronounceit.ankiaddon`. GitHub releases should attach that file as the downloadable Anki package.

Suggested next release tag:

```text
v1.0.1
```

Release focus:

- Adds Option/Alt-left-click audio-only pronunciation and Option/Alt-right-click popup pronunciation in the reviewer.
- Refreshes the settings dialog with clearer Review, Audio, Appearance, and Advanced sections.
- Adds theme presets for system, clinical light, slate, and high contrast reviewer popups.
- Keeps older config keys compatible while documenting the newer click modifier settings.
