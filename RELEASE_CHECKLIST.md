# Version 1.3.0 release record

The owner approved publication of the completed Kokoro audio pack and integration into the add-on on September 6, 2026. The exact 1,107,753,744-byte pack size is approved. Preserve all earlier releases and all generated audio checksums.

For this release, preserve v1.2.1 written guides, bind the version 3 manifest to the integrated dictionary, include the 155 matching recordings and attribution in the add-on, run automated and complete file checks, publish the pack, and verify the full anonymous download before releasing the matching add-on. The owner requested no further Anki launches; native validation of the final package is recorded as unrun. AnkiWeb publication is a separate task.

The historical checklist below describes the earlier version 2 workflow; its Azure-specific requirements do not govern the approved version 3 generation method or its approved pack size.

---

# PronounceIt Release Checklist

For release-prep merges to `main`, run the checks below before creating either
GitHub Release. AnkiWeb publication is explicitly out of scope for this release.

Run these checks before distributing `dist/pronounceit.ankiaddon`:

```bash
python3 -m unittest discover -s tests
python3 scripts/corpus/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests
python3 scripts/release/build_ankiaddon.py
unzip -l dist/pronounceit.ankiaddon
```

Manual Anki smoke test:

Use a disposable Anki base/profile copy, disable sync, and set a unique
`ANKI_SINGLE_INSTANCE_KEY`. Never run release acceptance against the live profile.
Before publishing, serve the exact local pack artifacts over a Range-capable local
HTTP server and install the exact candidate `.ankiaddon` into the disposable base.

1. Install or symlink the add-on into `addons21/pronounceit`.
2. Restart Anki.
3. Review a card with a known medical term, such as `agranulocytosis`.
4. Confirm Option/Alt gestures report “Reveal the answer first” before reveal when `allow_on_question_side` is explicitly `false`.
5. Reveal the answer, then hold Option/Alt and click the term; confirm audio plays once without opening the popup.
6. Hold Option/Alt while dragging across part of a word or phrase; confirm playback starts after selection and resolves the longest matching medical phrase, then complete word bounds.
7. Select the term normally, press and release Option/Alt, and confirm audio plays once. Confirm releasing Option/Alt after a modifier-click does not play twice.
8. Plain right-click the term and confirm Anki’s normal menu opens without PronounceIt actions or playback.
9. Control/Ctrl + click the term and confirm the PronounceIt submenu opens with Play, Details, and Save. Select the term, press Control/Ctrl, and confirm the same submenu opens.
10. Open Caleb M. Add-ons Settings > PronounceIt settings and confirm the activation-modifier selector and all groups render cleanly without horizontal scrolling.
11. Change between Light and Dark and confirm Settings, the reviewer popup, and notices retheme immediately and remain readable.
12. Hover or click a marked AMBOSS term, then use Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Search pronunciation and confirm the PronounceIt popup appears.
13. Use Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Search pronunciation and enter `agranulocytosis`.
14. Use Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Add custom pronunciation on a test term and confirm it is saved to `user_files/custom_pronunciations.json`.
15. Save the term, then open Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Saved pronunciations.
16. Pronounce a non-dictionary test word and confirm a cached clip appears in `user_files/generated_audio/` before any live TTS fallback is needed.
17. Open Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Dictionary audit and confirm it reports PASS.
18. Open Caleb M. Add-ons Settings > PronounceIt settings > Advanced > Pronunciation tools > Playback diagnostics and confirm recent playback attempts and any data warnings are readable.
19. In Offline pronunciation pack, start the complete pack download, close Settings, and confirm card review remains responsive while all 16 shards download in the background.
20. Reopen Settings and verify progress reconnects; test pause/resume, cancellation, interrupted Range resume, checksum failure, verification, update, removal, and low-space failure messaging.
21. Verify Custom, Azure, Generated, and Live audio plus diagnostics. Confirm bundled and downloaded clips report Azure, uncached pack terms extract on demand, and the 250 MiB LRU evicts old files.
22. Inspect Settings and reviewer UI in light/dark themes, keyboard navigation, and representative scaling. Capture acceptance screenshots.
23. Restart Anki twice and confirm saved/custom pronunciations, partial downloads, and installed pack state persist.
24. Confirm the isolated base contains all writes and sync remained disabled.

GitHub deployment gate:

- Merge the tested commit and rebuild both artifacts from that exact merge commit.
- Run `python3 scripts/release/publish_audio_pack.py` as a dry verification, then rerun with `--publish` only after `gh auth status` passes.
- Publish `audio-pack-v2` as non-latest and verify all 18 remote assets.
- Repeat the complete anonymous download from GitHub in the isolated profile.
- Only then push the current version tag; the release workflow builds and publishes `pronounceit.ankiaddon`.
- Do not create or update an AnkiWeb listing.

Pronunciation release gate:

- If `data/medical_pronunciation_lexicon_for_codex.txt` changes, run `python3 scripts/corpus/import_source_lexicon.py` before the checks above.
- If a high-yield pronunciation changes, run `python3 scripts/audio/generate_bundled_audio.py --force --high-yield --parallel` before the checks above.
- For a neural audio release, generate the 1,092-clip pilot, record the checksum-bound owner method approval, then confirm `python3 scripts/audio/review_audio.py status` reports `readyForFullGeneration: true`.
- Run full generation only after the pilot passes, then build with `python3 scripts/audio/build_audio_pack.py --pack-version 2 --base-url <v2-release-url> --install-high-yield`.
- The builder must reject generated G2P phonemes, stale method approval, mismatched SSML, invalid sidecars, and checksum or duration errors.
- The high-yield checklist must pass with no missing terms.
- The bundled dictionary must contain at least 590 unique terms and the checklist must contain at least 155 terms.
- The source lexicon in `data/medical_pronunciation_lexicon_for_codex.txt` must have no missing runtime dictionary terms.
- The source lexicon must have no pronunciation mismatches against the runtime dictionary.
- Every bundled term must include display pronunciation, syllables, stress capitalization, and TTS speech text.
- Every high-yield checklist term must have valid playable AIFF or MP3 audio.
- Every comprehensive-pack term must have one valid MP3 and metadata sidecar; all 16 deterministic shards must match `pack-manifest.json`, `SHA256SUMS`, and the dictionary hash.
- Confirm Azure credentials, build reports, pack shards, and private `user_files` content are absent from `dist/pronounceit.ankiaddon`.
- The archive must exclude zero-frame placeholders, generated caches, saved/custom JSON, backups, and private `user_files/audio` content.
- TTS speech text must not include capitals, hyphens, or alternate-pronunciation `or` text.
- New terms should be added to `data/high_yield_checklist.json` when they represent common medical-school review content.
