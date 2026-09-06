# Pronunciation source evidence

`audio-v1.3.0.json` is the byte-preserved original dictionary bound to the published v1.3.0 audio manifest. It is retained so the compact audio inventory can be verified against the same recording assets.

`written.json` retains selected source sounds, references, conversion records, corrections, and generation evidence. The written-source builder updates this file; `scripts/corpus/build_library.py` validates it and exports the compact runtime text plus source references. These source records are independent of user-facing term types.

`legacy-lexicon.txt` preserves the earlier input lexicon. It is historical evidence, not a second runtime term list. Nothing in this directory is shipped inside the add-on archive.
