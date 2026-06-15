# PronounceIt Release Checklist

For release-prep merges to `main`, run the checks below but do not create a
GitHub Release, do not create a `v1.1.0` tag, and do not upload to AnkiWeb until
the publish step is explicitly approved.

Run these checks before distributing `dist/pronounceit.ankiaddon`:

```bash
python3 -m unittest discover -s tests
python3 scripts/audit_pronunciations.py
node --check web/pronounceit.js
PYTHONPYCACHEPREFIX=/private/tmp/pronounceit_pycache python3 -m compileall __init__.py pronounceit scripts tests
python3 scripts/build_ankiaddon.py
unzip -l dist/pronounceit.ankiaddon
```

Manual Anki smoke test:

1. Install or symlink the add-on into `addons21/pronounceit`.
2. Restart Anki.
3. Review a card with a known medical term, such as `agranulocytosis`.
4. Confirm `Ctrl+P` / `Cmd+P` does not open pronunciation before revealing the answer when `allow_on_question_side` is `false`.
5. Reveal the answer, then Option/Alt-left-click the term and confirm audio plays without opening the popup.
6. Option/Alt-right-click the term and confirm the popup opens, autoplays audio, and shows the term, pronunciation, syllables, Play button, and save button.
7. Select the term and press `Ctrl+P` or `Cmd+P`, then confirm the popup still works for keyboard lookup.
8. Click Play and confirm the spoken audio follows the phonetic guide.
9. Open Tools > PronounceIt Settings... and confirm the Review, Audio, Appearance, and Advanced groups render cleanly.
10. Change the reviewer theme through each preset and confirm the popup remains readable.
11. Hover or click a marked AMBOSS term, then use Tools > PronounceIt Settings... > Advanced > Current Selection and confirm the PronounceIt popup appears.
12. Use Tools > PronounceIt Settings... > Advanced > Manual Lookup and enter `agranulocytosis`.
13. Use Tools > PronounceIt Settings... > Advanced > Custom Pronunciation on a test term and confirm it is saved to `user_files/custom_pronunciations.json`.
14. Save the term, then open Tools > PronounceIt Settings... > Advanced > Saved List.
15. Pronounce a non-dictionary test word and confirm a cached clip appears in `user_files/generated_audio/` before any live TTS fallback is needed.
16. Open Tools > PronounceIt: Dictionary Audit and confirm it reports PASS.

Pronunciation release gate:

- If `data/medical_pronunciation_lexicon_for_codex.txt` changes, run `python3 scripts/import_source_lexicon.py` before the checks above.
- If `data/medical_pronunciations.json` changes, run `python3 scripts/generate_bundled_audio.py --force` before the checks above.
- The high-yield checklist must pass with no missing terms.
- The bundled dictionary must contain at least 590 unique terms and the checklist must contain at least 155 terms.
- The source lexicon in `data/medical_pronunciation_lexicon_for_codex.txt` must have no missing runtime dictionary terms.
- The source lexicon must have no pronunciation mismatches against the runtime dictionary.
- Every bundled term must include display pronunciation, syllables, stress capitalization, and TTS speech text.
- Every bundled term must have a non-empty bundled audio file in `audio/`.
- TTS speech text must not include capitals, hyphens, or alternate-pronunciation `or` text.
- New terms should be added to `data/high_yield_checklist.json` when they represent common medical-school review content.
