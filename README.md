# PronounceIt

PronounceIt adds pronunciation help to Anki desktop while you review medical cards. One library covers **95,902 terms**, organized in two ways:

- **Written pronunciations** are included with the add-on. Capitals mark stress.
- **Audio pronunciations** are available in one separate, complete audio-library download, approximately **1.03 GiB**.

All terms use the same lookup and playback behavior. There are no high-yield groups, term quality tiers, or special bundled audio subsets. Written pronunciations and audio are maintained independently and can differ.

## Use PronounceIt

- Hold **Option/Alt** while clicking or selecting a term, or select text and tap the key, to hear it.
- Use **Control/Ctrl + click or right-click**, or select text and tap Control/Ctrl, to open a quick card and hear its pronunciation automatically. Use **Play** to repeat it or **Save** to keep the term.
- Plain right-click keeps Anki’s standard menu.

Search and quick cards show the written pronunciation. A quick card plays once when its lookup finishes, using the audio library or computer voice according to your settings. **Play** repeats the pronunciation; search results play when you press **Play**. **Details** shows the playback source. Quick cards fit their contents with compact spacing, and long pronunciations wrap inside the reviewer window. Closing a result does not play audio.

## Install

Build this checkout and install `dist/pronounceit.ankiaddon` through **Tools > Add-ons > Install from file...**, then restart Anki to load the update. Install over the existing PronounceIt add-on so its settings and `user_files/` directory are retained. This development update has not been published. The earlier [v1.3.0 release](https://github.com/caleblee789/PronounceIt/releases/download/v1.3.0/pronounceit.ankiaddon) and [AnkiWeb listing](https://ankiweb.net/shared/info/1352407063) are separate distribution channels.

Open **Caleb M. Add-ons Settings > PronounceIt settings > Audio > Download library** to get every audio pronunciation. The download runs in the background. Its 16 transport files are managed automatically as one library; there are no packs or categories to choose between.

The existing full v1.3.0 audio download remains compatible. Updating this add-on does not require downloading the same audio again. Without the download, written pronunciations remain available and the default playback mode uses your computer voice.

## Settings

Open **Caleb M. Add-ons Settings > PronounceIt settings**. The sidebar organizes settings into four sections, with related controls grouped into cards. The layout adapts to the available window width, and navigation and save controls stay visible while you scroll.

| Section | Controls |
| --- | --- |
| **Review** | Enable PronounceIt, choose playback and quick-card keys, allow pronunciation before revealing an answer, control quick-card behavior, and choose Light or Dark appearance. |
| **Audio** | Choose playback mode, manage the complete audio library, and adjust computer voice volume and speed with sliders. Advanced voice options are expandable. |
| **Tools** | Search, saved pronunciations, custom corrections, pronunciation-data checks, and audio troubleshooting. |
| **About & support** | Support the creator, open local files, and restore default settings. |

Pronunciation before revealing an answer is enabled by default. Turn it off in Review if hearing a term would reveal the answer.

Appearance changes preview immediately across settings and pronunciation cards. **Save changes** applies your draft and keeps the window open; it is enabled only when something has changed. **Discard changes** restores the saved settings and appearance. Closing with unsaved changes offers **Keep editing**, **Discard changes**, or **Save and close**. A failed save keeps your draft available and shows an error in the window.

Playback modes are **Audio, then computer voice**, **Audio only**, and **Computer voice only**. Audio uses a custom recording when provided, then the downloaded library. Audio-only mode disables Play when no suitable recording is available. Computer voice availability depends on your operating system; changing the text read aloud, voice, or speed selects a new speech-cache entry.

The first-run prompt offers the audio library once. Settings provides Download, Resume, Pause, Cancel download, Update, Check files, and Remove as appropriate. Downloads continue when Settings closes. Cancellation preserves partial files for resuming. Remove deletes installed and partial library files while preserving saved words and custom corrections. Downloads and extracted audio are checked against their checksums. The extracted cache defaults to 250 MiB; downloaded ZIP files are separate from that limit.

## Saved terms and custom corrections

In settings, use **Tools > Saved pronunciations > Open saved** to search saved words, play them, open the original card or note in Browse when available, or remove a word. The list expands with the window, and empty lists and unmatched searches have distinct guidance.

Use **Tools > Custom pronunciation > Add custom** to enter a term and its written pronunciation. A canonical term’s correction also applies to its aliases. **Additional options > Text read aloud** supplies an explicit computer-speech correction; leave it blank to retain normal audio. An explicit speech correction takes precedence over recordings and requires a mode that allows computer voice. Saving a pronunciation preserves its speech override for later playback.

User data lives in the add-on’s `user_files/` directory:

- `saved_pronunciations.json`: saved terms and available card, note, and deck metadata.
- `custom_pronunciations.json`: local written and speech corrections.
- `audio/`: custom recordings referenced by a custom entry’s `audioFile`.
- `audio_packs/`, `audio_cache/`, and `generated_audio/`: the downloaded library and playback caches.

These files survive add-on upgrades. They are local to the Anki installation and shared by profiles using the same add-ons directory; they are not synced through AnkiWeb. Saved/custom JSON updates are atomic and retain a `.bak` backup. Damaged JSON is left unchanged and reported through the interface. Existing custom entries and saved terms remain compatible, including legacy speech overrides and optional `syllables` fields.

## Support

The **Buy Me a Coffee** button stays in the settings footer, with another support link in **About & support**.

<a href="https://buymeacoffee.com/caleblee78f"><img src="pronounceit/assets/buy_me_a_coffee.png" alt="Buy Me a Coffee" width="140"></a>

## Development

The runtime has two inventories:

| File | Contents |
| --- | --- |
| `data/audio_pronunciations.json` | Canonical terms, aliases, and audio asset IDs. |
| `data/written_pronunciations.json` | A written pronunciation for each canonical term. |
| `data/audio-pack-release.json` | Checksums binding the audio inventory to the complete download. |
| `data/written-pronunciation-sources.json` | Per-term source references for attribution. |
| `quality/pronunciation_sources/` | Original audio contract and written-source evidence, outside the runtime package. |
| `quality/legacy_bundled_audio/` | Preserved evidence and clips from the retired bundled subset. |

`pronounceit/` contains lookup, playback, downloads, storage, and Qt dialogs; `web/` contains reviewer JavaScript and CSS. Settings live in `pronounceit/settings.py`, shared dialog components in `pronounceit/ui_components.py`, and the common Light/Dark palette in `pronounceit/theme.py`. The settings design adapts the owner's Home Screen Dashboard components with permission; PronounceIt remains independent and does not require that add-on. Current Kokoro generation tools live in `scripts/audio/`, written-source tools in `scripts/corpus/`, and packaging utilities in `scripts/release/`. Retired Azure generation tools remain in Git history.

### Validate and build without Anki

Use Python 3.11 or newer and Node.js, matching CI. Runtime code needs no pronunciation-generation dependencies.

```bash
python3 -m unittest discover -s tests
python3 scripts/corpus/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/tmp/pronounceit_pycache python3 -m compileall -q __init__.py pronounceit scripts tests
python3 scripts/release/build_ankiaddon.py
```

The builder checks complete audio and written inventories, the audio-release binding, required runtime files, and source notices. It includes no pronunciation recordings, source-review archives, or private user data. It replaces `dist/pronounceit.ankiaddon` only after validation succeeds. Identical inputs produce identical package bytes; use `--output /path/to/candidate.ankiaddon` to preserve another candidate.

Automated checks do not establish native Anki behavior or visual acceptance. [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) describes the later smoke test in a disposable, sync-disabled Anki base. The commands above do not launch Anki.

### Maintain the library

Written-source selection and review evidence stay outside the runtime term model. Rebuild from the pinned snapshots with the generation environment, then export the compact inventories against the exact published audio manifest:

```bash
.venv-generation/bin/python scripts/corpus/build_written_guides.py
python3 scripts/corpus/build_library.py --pack-manifest /path/to/published/pack-manifest.json
python3 scripts/corpus/audit_pronunciations.py
```

Dependencies are pinned in `scripts/corpus/requirements-written-guides.txt`. Source snapshots live under `build/kokoro-source-snapshots/` and `build/written-guide-sources/`. The exporter validates source reproducibility, term and alias coverage, and the published audio checksum before writing runtime data. Written-only edits leave audio compatibility unchanged. Audio changes require a matching library and release binding; see [OVERNIGHT_AUDIO_REBUILD.md](OVERNIGHT_AUDIO_REBUILD.md).

The current audio uses the accepted American English Kokoro voice. Ten pilot recordings were accepted; full-library pronunciation accuracy has not been individually measured. Source evidence and file integrity checks do not establish clinical accuracy. See [PRONUNCIATION_QA.md](PRONUNCIATION_QA.md) for the validation boundaries.

## License

Application code uses the MIT License. Written pronunciations have separate terms in [data/written-guide-attribution.md](data/written-guide-attribution.md), with original article references in `data/written-pronunciation-sources.json`. Audio has separate attribution and applicable licenses in [PRONUNCIATION_ASSET_ATTRIBUTION.md](PRONUNCIATION_ASSET_ATTRIBUTION.md) and `pronunciation_licenses/`.

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for development changes and the earlier published release.
