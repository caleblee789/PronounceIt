# Pronunciation QA

PronounceIt shows one readable pronunciation field. Display text lives in `data/written_pronunciations.json`, independently of the legacy audio corpus. Each text record retains the canonical term, a guide, an internal review status, and provenance. Published references take priority; unresolved terms use generated estimates marked `AI Generated` only in the data. Unknown lookups or damaged text data can still report unavailable text without disabling playback.

The legacy audio corpus continues to include:

- `term`: the selected card text to match.
- `pronunciation`: retained legacy input for audio compatibility; not the bundled display authority.
- Optional `syllables`: accepted for legacy compatibility; no longer displayed or required.
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

Audio metadata is independent of the displayed guide. Version 1.3.0 preserves the published v1.2.1 written guides while replacing only audio assets and associated provenance. Raw canonical term spelling remains the default system TTS fallback; space-separated respellings are used only for explicit user overrides. Custom recordings are preferred when referenced by an entry. An explicit user speech override bypasses recordings; a written-only correction leaves normal audio available.

The historical version 2 Azure pipeline uses raw-term SSML and manually reviewed SAPI corrections. Its approval cannot approve a version 3 Kokoro pack. Both manifest versions are supported only when the dictionary checksum matches.

The audit reports any zero-frame AIFF placeholders and the package builder excludes them. An AIFF is shippable only when its header reports at least one frame and its sound-data chunk is non-empty; release-ready checkouts should contain none.

Use explicit `sapiPhonemes` for reviewed synthesis corrections. Existing `speechText` remains supported for compatibility and explicit user overrides but is not the default fallback input.

## Adding Terms

1. Add the term to `data/medical_pronunciations.json`.
2. Add high-yield terms to `data/high_yield_checklist.json`.
3. Include aliases for abbreviations such as `GERD`, `TMJ`, or organism shorthand.
4. If updating from the source lexicon, run `python3 scripts/corpus/import_source_lexicon.py`.
5. Rebuild the written-guide inventory and matching audio-pack metadata before packaging. The current Kokoro workflow is described in `OVERNIGHT_AUDIO_REBUILD.md`; the Azure scripts are historical tooling and must not overwrite the current release.
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
- Every canonical term and alias survives the written-guide rebuild.
- Every dictionary-backed guide has a documented reference and matches its selected phonetics after conversion; composed guides cover every component.
- Every generated guide has explicit internal generation provenance, preserved input spelling, a checksummed generation manifest, and a reproducible phonetic conversion. AI-authored respellings retain their separate input file and checksum.
- Every canonical term has a nonempty written guide in the complete package. Unsupported reference symbols are rejected before trying later sources or generation. Generated output is not evidence that a dictionary attests that pronunciation.
- No generated/estimated status, separate syllable row, or speech-text row appears in pronunciation results. Advanced custom speech overrides remain editable.
- Automated completeness and phonetic-conversion checks do not measure linguistic accuracy; retain the actual sample-review inventory and findings separately.
- The audit separates unavailable text from malformed/missing text data. Invalid written-data files fail packaging while runtime audio remains usable.
- Source attribution and license notices are included in the add-on.
- Every high-yield checklist term has validated, playable AIFF or MP3 audio in `audio/`.
- The comprehensive manifest contains 95,902 collision-free assets across 16 checksum-validated shards.
- The built archive contains no audio-pack shards, generation credentials, build reports, invalid audio, or private `user_files` data.
- TTS speech text must be lowercase, hyphen-free, and must not include alternate-pronunciation wording such as `or`.
- Accepted written variants may differ from audio. The original dictionary, audio files, synthesis inputs, and audio identifiers must remain unchanged during text-only updates.
- The historical Azure-native method approval is bound to the 1,092 pilot MP3 checksums, SSML hashes, dictionary hash, voice, rate, and output format.
- The approval covers the synthesis method and pilot quality; it does not claim individual review of all 95,902 clips.
- Any pilot re-synthesis or SSML change invalidates the method approval automatically.
- The pack builder refuses release unless the method approval is current and every asset, sidecar, checksum, duration, and identifier validates.
- Regionally variable pronunciations should prefer common US medical-school usage and can be overridden through `user_files/custom_pronunciations.json`.

## Local Corrections

Use Caleb M. Add-ons Settings > PronounceIt settings > Tools > Add custom pronunciation when a term needs a local correction before the bundled dictionary is updated. Custom entries are stored in `user_files/custom_pronunciations.json` and override bundled entries immediately after saving.

Document broadly useful text corrections with their references in `data/written-guide-corrections.json`, then rebuild written guides. The source dictionaries normally take precedence; set `overrideReference` only for a documented source error. AI-authored corrections belong in `data/written-guide-ai-overrides.json` and only fill remaining gaps. Do not modify the legacy audio corpus to change display text.
