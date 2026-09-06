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

The current version 3 audio pack uses Kokoro-82M with phoneme input, the American English `af_heart` voice, speed 0.95, and 24 kHz mono MP3 encoding at 48 kbps. Ten exact pilot clips and the generation method were accepted. Every other recording remains individually unreviewed; reference-backed pronunciation inputs and generated estimates are reported separately.

Audio metadata is independent of the displayed guide. Version 1.3.0 preserves the published v1.2.1 written guides while replacing only audio assets and associated provenance. Raw canonical term spelling remains the default system TTS fallback; space-separated respellings are used only for explicit user overrides. Custom recordings retain highest precedence.

The historical version 2 Azure pipeline uses raw-term SSML and manually reviewed SAPI corrections. Its approval cannot approve a version 3 Kokoro pack. Both manifest versions are supported only when the dictionary checksum matches.

The audit reports any zero-frame AIFF placeholders and the package builder excludes them. An AIFF is shippable only when its header reports at least one frame and its sound-data chunk is non-empty; release-ready checkouts should contain none.

Use explicit `sapiPhonemes` for reviewed synthesis corrections. Existing `speechText` remains supported for compatibility and explicit user overrides but is not the default fallback input.

## Adding Terms

1. Add the term to `data/medical_pronunciations.json`.
2. Add high-yield terms to `data/high_yield_checklist.json`.
3. Include aliases for abbreviations such as `GERD`, `TMJ`, or organism shorthand.
4. If updating from the source lexicon, run `python3 scripts/corpus/import_source_lexicon.py`.
5. Dry-run, generate, and package neural audio with `scripts/audio/generate_neural_audio.py` and `scripts/audio/build_audio_pack.py`.
6. Run:

```bash
python3 scripts/corpus/audit_pronunciations.py
python3 -m unittest discover -s tests
python3 scripts/release/build_ankiaddon.py
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

Use Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Add custom pronunciation when a term needs a local correction before the bundled dictionary is updated. Custom entries are stored in `user_files/custom_pronunciations.json` and override bundled entries immediately after saving.

Promote a custom correction into `data/medical_pronunciations.json` when it is broadly useful for medical students, especially if it appears in common AnKing, UWorld-style, Sketchy, Pathoma, or shelf-review cards.
