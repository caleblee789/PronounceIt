# PronounceIt Release Checklist

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
5. Reveal the answer, then select the term and press `Ctrl+P` or `Cmd+P`.
6. Confirm the popup shows the term, pronunciation, syllables, Play button, and save button.
7. Click Play and confirm the spoken audio follows the phonetic guide.
8. Right-click selected text and confirm the native Anki context menu includes `Pronounce selected word`.
9. Hover or click a marked AMBOSS term, then use Tools > PronounceIt: Pronounce Current Selection and confirm the PronounceIt popup appears.
10. Use Tools > PronounceIt: Pronounce Manually and enter `agranulocytosis`.
11. Use Tools > PronounceIt: Add or Update Custom Pronunciation on a test term and confirm it is saved to `user_files/custom_pronunciations.json`.
12. Save the term, then open Tools > PronounceIt: Saved Pronunciations.
13. Pronounce a non-dictionary test word and confirm a cached clip appears in `user_files/generated_audio/` before any live TTS fallback is needed.
14. Open Tools > PronounceIt: Dictionary Audit and confirm it reports PASS.

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
