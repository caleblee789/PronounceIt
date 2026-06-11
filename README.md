# PronounceIt

PronounceIt is an Anki desktop add-on for medical students who want fast, answer-side pronunciation help while reviewing cards. Select a word or short medical phrase after revealing an answer, press `Ctrl+P` / `Cmd+P`, or use the right-click/control-click quick menu, and PronounceIt opens a compact reviewer pop-up with a student-friendly pronunciation guide, syllable breakdown, and replayable audio.

The add-on is designed for review flow: quick to invoke, quiet when the answer is still hidden, and backed by a large bundled pronunciation corpus so common medical, pharmacology, anatomy, pathology, and clinical terms can play without relying on raw system text-to-speech.

## Highlights

- Reviewer-first lookup for selected words and short phrases.
- Answer-side lookup by default, with an option to allow question-side lookup.
- `Ctrl+P` / `Cmd+P` hotkey using Anki's `Mod+P` convention.
- AMBOSS-style floating pop-up anchored near the selected text.
- JavaScript reviewer quick menu with Play and save actions.
- Native Anki webview context-menu fallback for selected text.
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
3. Select a term, such as `agranulocytosis`.
4. Press `Ctrl+P` on Windows/Linux or `Cmd+P` on macOS.
5. Use the pop-up Play button to replay the audio.
6. Use the save button to add useful terms to the local saved pronunciation list.

You can also right-click/control-click selected text and choose the PronounceIt action, or use Tools > PronounceIt > Pronounce Current Selection.

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

Key settings:

- `enabled`: turns reviewer integration on or off.
- `hotkey`: defaults to `Mod+P`, which maps to Ctrl on Windows/Linux and Cmd on macOS.
- `audio_backend`: defaults to `local_audio_then_tts`.
- `allow_on_question_side`: defaults to `false` so lookup starts after the answer is revealed.
- `show_context_menu`: controls the custom right-click/control-click action.
- `show_save_button`: controls the saved-pronunciation button in the pop-up.
- `auto_close_on_card_change`: closes the pop-up when Anki advances to another card.
- `tts_voice`, `tts_rate`, `tts_volume`: tune fallback system TTS where supported.
- `unknown_term_message`: controls the pop-up text for terms not found in the bundled dictionary.

Supported audio backend values:

- `local_audio_then_tts`: play bundled audio first, generate a cached local clip for unbundled terms when possible, then fall back to system TTS.
- `local_audio`: require bundled or generated local audio.
- `system_tts`: skip local audio and use system TTS directly.

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
5. Review a card, reveal the answer, select a medical term, and press `Ctrl+P` / `Cmd+P`.

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

Suggested first release tag:

```text
v1.0.0
```
