# Pronunciation QA

PronounceIt ships student-friendly pronunciation guides rather than IPA. Each bundled term must include:

- `term`: the selected card text to match.
- `pronunciation`: readable phonetics with stressed syllables capitalized.
- `syllables`: syllable breakdown.
- Optional `speechText`: exact audio-generation and TTS-friendly text when the generated audio needs a manual override.
- Optional `audioFile`: relative path to a bundled or user-provided audio clip.
- Runtime `qualityTier`: `verified`, `curated`, `generated`, or `fallback`.
- Optional `sapiPhonemes`: reviewed Azure en-US SAPI phonemes for corrected single-word terms.
- Optional `sapiSegments`: reviewed `{text, sapi}` segments for corrected multiword terms.
- Optional `aliases`: common abbreviations, alternate spellings, or plural forms when automatic plural fallback is not enough.

## Audio Rule

The 155 high-yield checklist terms are bundled locally. The separately downloaded comprehensive pack contains one fluent neural MP3 for every dictionary term.

- Display: `uh-gran-yoo-loh-sy-TOH-sis`
- Legacy phonetic speech text: `uh gran yoo loh sy toh sis`
- Fluent fallback input: `agranulocytosis`

Space-separated respellings must not be sent to ordinary system TTS because they create a pause between every syllable. Neural release audio uses raw term spelling as one fluent SSML phrase by default. A `<phoneme>` element is permitted only for a manually reviewed correction. General-English G2P output must never control release audio. Runtime resolution is custom audio, reviewed bundled audio, reviewed comprehensive pack, generated cache, then raw-term system TTS.

The audit reports any zero-frame AIFF placeholders and the package builder excludes them. An AIFF is shippable only when its header reports at least one frame and its sound-data chunk is non-empty; release-ready checkouts should contain none.

Use explicit `sapiPhonemes` for reviewed synthesis corrections. Existing `speechText` remains supported for compatibility and explicit user overrides but is not the default fallback input.

## Adding Terms

1. Add the term to `data/medical_pronunciations.json`.
2. Add high-yield terms to `data/high_yield_checklist.json`.
3. Include aliases for abbreviations such as `GERD`, `TMJ`, or organism shorthand.
4. If updating from the source lexicon, run `python3 scripts/import_source_lexicon.py`.
5. Dry-run, generate, and package neural audio with `scripts/generate_neural_audio.py` and `scripts/build_audio_pack.py`.
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
- Every high-yield checklist term has validated, playable AIFF or MP3 audio in `audio/`.
- The comprehensive manifest contains 95,902 collision-free assets across 16 checksum-validated shards.
- The built archive contains no audio-pack shards, generation credentials, build reports, invalid audio, or private `user_files` data.
- TTS speech text must be lowercase, hyphen-free, and must not include alternate-pronunciation wording such as `or`.
- Audio for known terms follows the phonetic guide closely enough for a medical student to imitate.
- The Azure-native method approval is bound to the 1,092 pilot MP3 checksums, SSML hashes, dictionary hash, voice, rate, and output format.
- The approval covers the synthesis method and pilot quality; it does not claim individual review of all 95,902 clips.
- Any pilot re-synthesis or SSML change invalidates the method approval automatically.
- The pack builder refuses release unless the method approval is current and every asset, sidecar, checksum, duration, and identifier validates.
- Regionally variable pronunciations should prefer common US medical-school usage and can be overridden through `user_files/custom_pronunciations.json`.

## Local Corrections

Use Tools > PronounceIt: Add or Update Custom Pronunciation when a term needs a local correction before the bundled dictionary is updated. Custom entries are stored in `user_files/custom_pronunciations.json` and override bundled entries immediately after saving.

Promote a custom correction into `data/medical_pronunciations.json` when it is broadly useful for medical students, especially if it appears in common AnKing, UWorld-style, Sketchy, Pathoma, or shelf-review cards.
