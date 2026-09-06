# Audio library generation

The current full audio library is already published and remains compatible with the simplified runtime inventories. No audio regeneration is needed for this update. Existing prepared runs and acceptance records are historical evidence; they are bound to their original source files and must not be relabeled as approval for changed inputs.

## Future audio changes

Current tools prepare and generate the entire canonical inventory, then build one complete audio-library download and its matching add-on. There is no bundled clip subset.

- `scripts/corpus/kokoro_sources.py` prepares phoneme inputs, source provenance, and term/alias bindings.
- `scripts/audio/kokoro_pilot.py` generates and verifies a bounded voice pilot.
- `scripts/audio/kokoro_rebuild.py` checks preparation, readiness, resumability, decoding, and generation identities.
- `scripts/audio/kokoro_pack.py` writes all 16 transport files, validates each asset and checksum, and stages the compact audio and written inventories with the exact new manifest binding.
- `scripts/release/publish_audio_pack.py --artifacts /path/to/audio-pack` verifies the complete candidate. Publication requires its separate `--publish` option and authorization.

Prepare a fresh run and verify its exact pilot and runtime bindings before using **Start Overnight Audio Rebuild.command**. Its `--check` option checks readiness without starting synthesis. Current source changes deliberately invalidate older readiness snapshots. Do not overwrite frozen runs or reuse old approval for changed inputs, voice settings, encoding, or generation code.

The launcher keeps the Mac awake, limits CPU concurrency, records progress, and resumes only unchanged, checksum-valid clips. Control-C stops the run; completed outputs are preserved. Keep the Mac plugged in with its lid open and ensure adequate disk space. The previous full run's 12–14 hour estimate and roughly 2 GB preflight memory measurement are historical observations, not guarantees for a new run.

The existing launcher defaults to `build/kokoro-rebuild/run-2026-09-05/`; a future rebuild must use a fresh prepared run directory. The finished candidate contains a `.ankiaddon` file, an `audio-pack/` directory, and separate pronunciation provenance and quality reports. It does not install into Anki or publish anything automatically.

## Validation

The accepted Kokoro pilot contains ten exact recordings. This is not a measured accuracy rate for the full library. Source variants, generated estimates, unresolved inputs, checksums, and review records remain in developer evidence, outside the runtime term model.

Any new complete audio candidate needs matching term and alias coverage, full decoding and checksum validation, current pilot acceptance, appropriate size approval, and the deferred native checks in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Preserve all previously published assets and reports.
