# Unreleased

This development update simplifies PronounceIt to audio pronunciations and written pronunciations for all 95,902 terms. The complete audio library remains one separate download, using the existing v1.3.0 audio unchanged.

- Removes high-yield groups, term quality tiers, and the 155-clip bundled subset from the runtime and package.
- Stores compact audio and written inventories; preserves attribution and source-review evidence separately.
- Retains compatibility with already downloaded v1.3.0 audio through an exact manifest and inventory binding.
- Applies canonical custom corrections to their aliases.
- Makes search playback explicit and keeps saved words, custom corrections, and long quick-card results usable in the revised interface.
- Honors audio-only playback and explicit custom speech corrections, including saved corrections.
- Refreshes computer-speech caches when text, voice, or speed changes; restores default Qt voice and speed correctly.
- Recovers interrupted and corrupt pack downloads, preserves cancellation, and removes partial packs when requested.
- Reports settings write failures instead of claiming success and permits enabling reviewer integration without a webview reload.
- Preserves deterministic packaging, includes both audio and written-guide source notices, excludes private data, and replaces an existing build only after validation succeeds.

Validation is limited to automated checks and package inspection until the native smoke test in `RELEASE_CHECKLIST.md` is performed. Anki was not launched for this review. No new release tag or public add-on package is published by this source merge.

# PronounceIt v1.3.0

Version 1.3.0 replaces the complete audio collection with the accepted American English Kokoro voice and connects the add-on to its matching download pack.

- 95,902 MP3 recordings, with 155 included in the add-on and the full collection in 16 download files.
- Approximately 1.03 GiB for the full pack; this exact size was approved by the owner.
- Preserves the written guides from v1.2.1, every canonical term and alias, custom overrides, saved words, and existing playback controls.
- Supports version 3 provenance and clip checksum metadata while retaining version 2 compatibility for matching older dictionaries.
- Checks cached recordings against the current clip checksum so an older clip cannot hide a correction.
- Keeps the download in its cancelling state when an in-flight transfer reports final progress.
- Shows only Word and Pronunciation in the details window, with wrapping for long guides.
- Includes pronunciation-source attribution and applicable asset licenses separately from the application code license.

The ten pilot recordings and voice were accepted. Reference-backed inputs and unverified estimates are separated in `quality/kokoro_rebuild/release-v1.3.0.json`; successful synthesis is not a whole-library accuracy measurement.

Validation covers the automated regression suite, the complete dictionary audit, all audio decoding and checksums, exact term and alias coverage, the bundled audio set, download-pack compatibility, and anonymous public downloads. Native Anki validation of this final package was not run at the owner's request.

Install the add-on package, restart Anki, then use Download/Update under Offline pronunciation pack in settings to install the full new collection. Earlier releases remain available. AnkiWeb publication is separate from this GitHub release.
