# PronounceIt

PronounceIt adds pronunciation help to Anki desktop while you review medical cards. It includes **95,902 terms**, a readable written guide for each term, **155 bundled recordings**, and an optional offline audio pack.

- Hold **Option/Alt** while clicking or selecting a term, or select text and tap the key, to hear it.
- Use **Control/Ctrl + click or right-click**, or select text and tap Control/Ctrl, to open a quick card with **Play** and **Save**.
- Plain right-click keeps Anki’s standard menu.

Capitals in written guides mark stress. Written guides and recordings are maintained separately and can differ. The current recordings use the accepted American English Kokoro voice; ten pilot recordings were accepted. The full library has not been individually checked for pronunciation accuracy.

## Install

For the published release, download [PronounceIt v1.3.0](https://github.com/caleblee789/PronounceIt/releases/download/v1.3.0/pronounceit.ankiaddon). The [AnkiWeb listing](https://ankiweb.net/shared/info/1352407063) is a separate distribution channel.

For the current development version described below, build this checkout and install `dist/pronounceit.ankiaddon` through **Tools > Add-ons > Install from file...**, then restart Anki. Merging source changes does not publish a new release.

The add-on includes 155 recordings. The optional full pack contains 95,902 recordings across 16 files and downloads approximately **1.03 GiB**. It is downloaded separately and is never embedded in the add-on archive.

## Settings and tools

Open **Caleb M. Add-ons Settings > PronounceIt settings** from Anki’s menu bar. Settings has three tabs:

| Tab | Controls |
| --- | --- |
| **Review** | Enable PronounceIt, choose playback and quick-card keys, allow pronunciation before revealing an answer, show Save, and choose Light or Dark appearance. |
| **Audio** | Choose playback sources, manage the offline pack, and set computer voice, speed, and volume where supported. |
| **Tools** | Search, saved pronunciations, custom corrections, library checks, audio troubleshooting, and local file shortcuts. |

Pronunciation before revealing an answer is enabled by default. Turn it off on the Review tab if hearing a term would reveal the answer. Appearance changes preview immediately; **Save** keeps settings and **Cancel** discards the draft. A failed settings save leaves the draft open.

Search and quick cards show a written guide with explicit **Play** and **Save** actions. Closing a result does not play audio. **Details** identifies the audio source. Long terms wrap inside the reviewer window.

## Playback and offline recordings

Audio sources are labeled **Custom audio**, **Recorded audio**, or **Computer voice**. Recorded audio includes the bundled clips and matching downloaded pack.

- **Recordings, then computer voice:** use an available recording, otherwise use computer speech.
- **Recordings only:** play recordings without generating computer speech. Play is unavailable when there is no suitable recording.
- **Computer voice only:** use your system’s speech service without using the recordings.

Computer voice availability depends on your operating system. Cached computer speech is kept separately from recordings; changing the text read aloud, voice, or speed selects a new cache entry.

The first-run prompt offers the offline pack once. **Audio** provides Download, Resume, Pause, Cancel download, Update, Check files, and Remove as appropriate. Downloads continue when Settings closes. Cancelling keeps partial files for a later resume; Remove deletes installed and partial pack files while preserving saved words and custom corrections. Interrupted downloads resume, and corrupt completed parts are downloaded again.

The add-on selects its matching version 3 pack from `data/audio-pack-release.json`. Downloaded shards and extracted clips are checked against the pack’s checksums. Older version 2 packs remain supported for matching older dictionaries. The extracted clip cache defaults to 250 MiB; downloaded ZIP files are separate from that limit.

## Saved pronunciations and custom corrections

Use **Tools > Saved pronunciations** to search saved words, play them, open the original card or note in Browse when available, or remove a word.

Use **Tools > Add custom pronunciation** to enter a term and its written pronunciation. **Additional options > Text read aloud** supplies an explicit computer-speech correction; leave it blank to retain normal audio. An explicit speech correction takes precedence over recordings and requires a mode that allows computer voice. Saving a pronunciation preserves its speech override for later playback.

User data lives in the add-on’s `user_files/` directory:

- `saved_pronunciations.json`: saved terms and available card, note, and deck metadata.
- `custom_pronunciations.json`: local written and speech corrections.
- `audio/`: custom recordings referenced by a custom entry’s `audioFile`.
- `audio_packs/`, `audio_cache/`, and `generated_audio/`: downloaded packs and playback caches.

These files survive add-on upgrades. They are local to the Anki installation and shared by profiles that use the same add-ons directory; they are not synced through AnkiWeb. Saved/custom JSON updates are atomic and retain the previous file as a `.bak` backup. Damaged JSON is left unchanged and reported through the interface. Existing custom entries with `syllables` remain compatible, although syllables are no longer displayed separately.

## Development

### Project layout

- `pronounceit/`: dictionary lookup, playback, downloads, storage, and Qt dialogs.
- `web/`: reviewer JavaScript and CSS.
- `data/medical_pronunciations.json`: canonical terms and the published audio contract.
- `data/written_pronunciations.json`: written guides with references or generation provenance.
- `data/audio-pack-release.json`: matching published pack metadata.
- `audio/`: the 155 bundled recordings.
- `scripts/release/`: deterministic add-on packaging and release utilities.
- `scripts/audio/`: audio preparation, generation, pilot review, and pack building.
- `scripts/corpus/`: written-guide generation, source import, and audits.
- `tests/`: automated checks that run without launching Anki.

### Validate and build without Anki

Use Python 3.11 or newer and Node.js, matching the CI environment. Runtime add-on code needs no pronunciation-generation dependencies.

```bash
python3 -m unittest discover -s tests
python3 scripts/corpus/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/tmp/pronounceit_pycache python3 -m compileall -q __init__.py pronounceit scripts tests
python3 scripts/release/build_ankiaddon.py
```

The builder validates written-guide coverage, the dictionary’s audio-pack checksum, the bundled audio set, required runtime files, and source notices. It excludes private user data and only replaces `dist/pronounceit.ankiaddon` after validation succeeds. Identical input files produce identical package bytes. Use `--output /path/to/candidate.ankiaddon` to preserve another candidate.

Automated checks do not establish native Anki behavior or visual acceptance. Follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for a later smoke test in a disposable, sync-disabled Anki base. No Anki launch is needed for the commands above.

### Written-guide maintenance

Written guides prefer published references, then documented composition and corrections, followed by generated estimates. Provenance and generation status are retained in the data. Structural audits check completeness and reproducibility; they do not measure medical pronunciation accuracy.

Rebuild from the pinned source snapshots using the existing generation environment:

```bash
.venv-generation/bin/python scripts/corpus/build_written_guides.py
python3 scripts/corpus/audit_pronunciations.py
```

Dependencies are pinned in `scripts/corpus/requirements-written-guides.txt`. The builder expects the local Wiktionary and CMUdict snapshots under `build/kokoro-source-snapshots/`, plus checksummed supplemental sources under `build/written-guide-sources/`. `scripts/corpus/fetch_written_sources.py` fetches the supplemental sources. See [PRONUNCIATION_QA.md](PRONUNCIATION_QA.md) for correction and acceptance rules.

Keep display-only changes in the written-guide overlay. Changing `data/medical_pronunciations.json` changes the audio compatibility checksum and requires a matching pack. Audio regeneration and pilot acceptance are separate workflows; the tools and historical approvals are described in [OVERNIGHT_AUDIO_REBUILD.md](OVERNIGHT_AUDIO_REBUILD.md) and the pronunciation QA document.

## License

Application code uses the MIT License. Written guides have separate terms in [data/written-guide-attribution.md](data/written-guide-attribution.md). Audio-derived assets have separate attribution and applicable licenses in [PRONUNCIATION_ASSET_ATTRIBUTION.md](PRONUNCIATION_ASSET_ATTRIBUTION.md) and `pronunciation_licenses/`.

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for development changes and the published v1.3.0 release.
