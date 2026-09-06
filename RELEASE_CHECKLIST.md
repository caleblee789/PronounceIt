# PronounceIt Release Checklist

Source review and merge can be completed without launching Anki. Native acceptance and public distribution are separate gates. The current review explicitly defers Anki testing and does not authorize a new release or AnkiWeb upload.

## Automated source and package checks

```bash
python3 -m unittest discover -s tests
python3 scripts/corpus/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/tmp/pronounceit_pycache python3 -m compileall -q __init__.py pronounceit scripts tests
python3 scripts/release/build_ankiaddon.py
```

- Verify 95,902 canonical terms, all aliases, 155 high-yield terms, and complete written-guide coverage.
- Keep the released dictionary, `data/audio-pack-release.json`, and bundled recordings consistent. Display-only updates must not change the audio dictionary checksum.
- Validate referenced written-guide conversions, generated-guide provenance, and the checked-in corrections. Passing an audit does not establish linguistic accuracy.
- Require all Python/UI/web dependencies, written-guide data, audio provenance, and both sets of source attribution and license notices in the archive.
- Verify the archive contains exactly the 155 expected playable bundled recordings and excludes private user files, backups, caches, credentials, scripts, and build reports.
- Build a second archive with `--output` and confirm the package bytes match when source files are unchanged.
- Record the tested commit and candidate checksum. Preserve earlier packages and evidence.

## Deferred native Anki smoke test

Run only when authorized. Use a fresh disposable Anki base/profile, disable sync, and set a unique `ANKI_SINGLE_INSTANCE_KEY`. Install the exact candidate archive. Never use the normal collection for release acceptance.

1. Verify the process, visible window, filesystem writes, and sync settings identify the disposable base.
2. Review known, unknown, long, and multiword terms. Test before and after answer reveal, including the setting that blocks pre-answer pronunciation.
3. Verify Option/Alt click, selection, and modifier-tap playback; Control/Ctrl click, right-click, and modifier-tap quick cards; and Anki’s unchanged plain right-click. Check that each gesture plays at most once.
4. Test nested card markup and AMBOSS-wrapped terms, phrase boundaries, viewport edges, and theme changes.
5. Open all three settings tabs and owned dialogs in Light and Dark, at normal and compact sizes. Check keyboard navigation, scrolling, wrapping, and focus. Capture native acceptance screenshots.
6. Confirm Search plays only after Play. Save a word, filter the saved list, play it, open its original card in Browse, and remove it.
7. Add a written-only custom correction and confirm normal recordings still play. Add explicit text read aloud and confirm it overrides recordings, survives saving, and changes when edited. Clear it to restore normal audio.
8. Confirm Recordings only never invokes computer speech, including modifier playback and saved words. Test computer-only and mixed modes; change and reset voice, speed, and volume where supported.
9. Save and cancel settings drafts. Test a save failure, then retry. Disable and re-enable pronunciation while reviewing.
10. Download the matching pack, close/reopen Settings, pause, resume, and cancel. Restart and resume partial files. Test corrupt downloads, Check files, low-space errors, and Remove after both completed and cancelled downloads.
11. Confirm the full pack resolves uncached terms, reports the actual playback source, and respects the extraction-cache limit. Verify custom recordings and system-voice fallback independently.
12. Restart twice. Recheck saved/custom data, settings, pack status, the isolated process and base, and disabled sync. Record all unrun or failed gates separately.

A Range-capable local server can exercise interruption and corruption before testing anonymous downloads from the published pack URL.

## Public distribution

- Obtain native acceptance for the exact release candidate before a new public release.
- Retain immutable existing release tags and assets. Do not overwrite v1.3.0 or its matching audio pack.
- A source-only change can continue using the existing version 3 pack when the audio dictionary checksum is unchanged.
- Audio changes require their own pilot approval, provenance, full decoding/checksum validation, matching dictionary and pack metadata, and explicit publication authorization. Historical Azure approval does not approve Kokoro audio.
- Publish a new immutable pack only when needed, verify anonymous downloads, then tag the approved add-on version. A version tag triggers `.github/workflows/release-addon.yml`.
- AnkiWeb publication requires a separate request. A merge, passing CI, or a valid archive does not establish native or human acceptance.
