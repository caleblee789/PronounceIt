# Pronunciation validation

The application uses one term library with audio pronunciations and written pronunciations. Term categories and quality tiers are not part of its runtime model.

## Runtime data

- `data/audio_pronunciations.json` contains canonical terms, aliases, and stable audio asset IDs.
- `data/written_pronunciations.json` contains the corresponding written pronunciations in the same canonical order. Its identity checksum binds both terms and aliases.
- `data/audio-pack-release.json` binds the audio inventory to the exact complete audio-library manifest. The existing v1.3.0 audio is unchanged; its original dictionary checksum is retained as a compatibility identifier.
- `data/written-pronunciation-sources.json` preserves the references required for attribution. Source selection, conversion, and review evidence live in `quality/pronunciation_sources/` and are not term labels.

Written pronunciation changes never feed speech or cache keys. Computer voice reads the canonical term unless the user supplies an explicit **Text read aloud** override. Custom recordings take precedence over the audio library; an explicit speech override takes precedence over both and requires computer voice to be enabled. Old saved/custom JSON remains readable without rewriting the user's files during an upgrade.

## Automated checks

```bash
python3 -m unittest discover -s tests
python3 scripts/corpus/audit_pronunciations.py
python3 scripts/release/build_ankiaddon.py
```

The runtime audit verifies unique audio asset IDs, canonical term and alias integrity, complete written coverage, and the released audio binding. It reports two counts: audio pronunciations and written pronunciations. A damaged written file is reported while audio lookup remains usable. Packaging requires both complete inventories.

The source exporter, `scripts/corpus/build_library.py`, additionally validates written-source evidence with `scripts/corpus/written_sources.py`: selected source phonetics must reproduce their guides, corrections must retain their references, and generation inputs must match their recorded checksums. It verifies every canonical audio ID against the published manifest before binding the compact inventory. This preserves the full existing download without regenerating recordings.

The deterministic package builder includes required runtime modules, both inventories, and attribution notices. It rejects pronunciation audio, legacy subsets, private user files, caches, scripts, and quality records inside the add-on archive. Every recording is supplied through the one separate library download or the user's custom files.

## Audio generation and historical evidence

The current complete audio library contains 95,902 Kokoro-82M recordings using phoneme input, the American English `af_heart` voice, speed 0.95, and 24 kHz mono MP3 encoding at 48 kbps. The ten exact pilot recordings and generation method were accepted. The other recordings have not been individually listened to. The released library is about 1.03 GiB.

Kokoro preparation and candidate generation cover the complete library. Source provenance, unresolved-input records, pilot acceptance, per-clip checksums, and generation bindings remain developer validation records. They do not create separate term groups. Audio changes require a new matching manifest; published recordings and release evidence must not be overwritten by a written-only update.

The retired subset's original clips and records are preserved under `quality/legacy_bundled_audio/`. Historical releases retain their original manifests and reports. Old version 2 download compatibility remains for older dictionary-based installations, but the obsolete Azure generation and subset-packaging scripts have been retired.

## Acceptance boundaries

Structural validation proves file integrity, coverage, source reproducibility, and compatibility. It does not measure linguistic or clinical correctness. Source-backed entries, generated estimates, and accepted pilot clips remain distinguishable in developer evidence, without appearing as user-facing categories.

Native playback, layout, settings persistence, reviewer behavior, and human acceptance require the separate disposable-profile smoke test in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Anki was not launched during this source review and simplification. No audio was regenerated or publicly released.
