# Pronunciation QA

PronounceIt ships student-friendly pronunciation guides rather than IPA. Each bundled term must include:

- `term`: the selected card text to match.
- `pronunciation`: readable phonetics with stressed syllables capitalized.
- `syllables`: syllable breakdown.
- Optional `speechText`: exact audio-generation and TTS-friendly text when the generated audio needs a manual override.
- Optional `audioFile`: relative path to a bundled or user-provided audio clip. Bundled entries use the default `audio/<term-slug>.aiff`.
- Optional `aliases`: common abbreviations, alternate spellings, or plural forms when automatic plural fallback is not enough.

## Audio Rule

Known terms are bundled as local AIFF audio generated from normalized phonetic text derived from `pronunciation`, not from raw spelling. For example:

- Display: `uh-gran-yoo-loh-sy-TOH-sis`
- Bundled/audio fallback speech text: `uh gran yoo loh sy toh sis`

This is intentional. Raw system TTS often misreads medical spelling. The default audio backend is `local_audio_then_tts`, so bundled audio is attempted first, unbundled terms are generated into `user_files/generated_audio/`, and system TTS is used only if local audio cannot be generated or played.

Use explicit `speechText` for exceptions where the displayed pronunciation is clear for students but the system voice needs a different cue. Keep it lowercase, space-separated, and free of stress capitals.

## Adding Terms

1. Add the term to `data/medical_pronunciations.json`.
2. Add high-yield terms to `data/high_yield_checklist.json`.
3. Include aliases for abbreviations such as `GERD`, `TMJ`, or organism shorthand.
4. If updating from the source lexicon, run `python3 scripts/import_source_lexicon.py`.
5. Regenerate bundled audio with `python3 scripts/generate_bundled_audio.py --force`.
6. Run:

```bash
python3 scripts/audit_pronunciations.py
python3 -m unittest discover -s tests
python3 scripts/build_ankiaddon.py
```

## Acceptance Criteria

- The audit reports `passed: true`.
- The bundled dictionary contains at least 590 unique terms.
- The high-yield checklist contains at least 155 terms and has no missing terms.
- Every term in `data/medical_pronunciation_lexicon_for_codex.txt` resolves in the runtime dictionary.
- Every source lexicon term keeps the same student-facing pronunciation in the runtime dictionary.
- Every bundled term has a stress marker, pronunciation, syllables, and speech text.
- Every bundled term has a non-empty audio file in `audio/`.
- TTS speech text must be lowercase, hyphen-free, and must not include alternate-pronunciation wording such as `or`.
- Audio for known terms follows the phonetic guide closely enough for a medical student to imitate.
- Regionally variable pronunciations should prefer common US medical-school usage and can be overridden through `user_files/custom_pronunciations.json`.

## Local Corrections

Use Tools > PronounceIt: Add or Update Custom Pronunciation when a term needs a local correction before the bundled dictionary is updated. Custom entries are stored in `user_files/custom_pronunciations.json` and override bundled entries immediately after saving.

Promote a custom correction into `data/medical_pronunciations.json` when it is broadly useful for medical students, especially if it appears in common AnKing, UWorld-style, Sketchy, Pathoma, or shelf-review cards.
