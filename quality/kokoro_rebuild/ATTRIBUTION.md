# Pronunciation asset attribution

This notice applies to the newly derived pronunciation records and recordings
in the Kokoro candidate. PronounceIt application code retains its separate
LICENSE. The generation models and tools are not bundled with the Anki add-on.

The newly derived pronunciation assets are distributed under
[Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Retain this attribution, identify subsequent changes, and distribute adaptations
of these assets under the same license. No source publisher endorses this work.

## Wiktionary contributors

English Wiktionary pronunciations are extracted through
[Wiktextract / Kaikki](https://kaikki.org/dictionary/rawdata.html), from the
2026-08-05 Wikimedia dump, extracted 2026-08-28. The extraction reports
Wiktextract revision 872fc7b. The exact downloaded bytes and other source
snapshots are identified by SHA-256 in prepared.json.

Each selected Wiktionary pronunciation record retains its entry URL, US usage
tags, original IPA, and source line. The entry's history provides contributor
attribution. IPA has been converted into Kokoro symbols and stress placement;
word pronunciations may be combined for multiword terms. Record selection and
generated audio are PronounceIt adaptations. Accepted variants may remain in
the provenance report.

[Wikimedia licensing](https://dumps.wikimedia.org/legal.html) provides the source
text under CC BY-SA 4.0 (with additional GFDL availability where applicable).
This distribution uses CC BY-SA 4.0. Original reference-site recordings and
definitions are not redistributed.

## CMU Pronouncing Dictionary

[CMUdict](https://github.com/cmusphinx/cmudict), maintained by the Speech Group
at Carnegie Mellon University, snapshot
74790861f652b15e4ac49015a90074ad62a27690. Selected ARPABET pronunciations are
converted into Kokoro symbols. The complete CMUdict copyright, conditions, and
disclaimer accompany these assets in CMUdict-LICENSE.

## Local generation and estimates

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), by hexgrad, model revision
f3ff3571791e39611d31c381e3a41a3af07b4987, uses the af_heart American English voice
at speed 0.95. The model card identifies the weights as Apache-2.0. The pinned
configuration, weight and voice hashes, inference settings, dependency versions,
and accepted pilot binding accompany the candidate.

[Misaki](https://github.com/hexgrad/misaki) 0.9.4 supplies local US pronunciation
estimates. Its Apache-2.0 license is retained as Misaki-LICENSE. The local
[eSpeak NG](https://github.com/espeak-ng/espeak-ng) fallback runs only during
input preparation. These tools and their runtime libraries are not distributed
inside the Anki add-on. Their estimates are explicitly unverified.

## Reviewed corrections and pilot references

Existing manual audio corrections are preserved with their source phonemes.
The ten accepted pilot entries retain their individual reference links and
short transcriptions in pilot-spec.json and pilot-manifest.json. Publisher
definitions and original recordings are not included. The user's acceptance
applies to those exact ten generated clips and their generation method; it is
not an accuracy measurement for the remaining library.

The pronunciation-provenance directory retains the complete derived input
records, source snapshot hashes, approval evidence, variants, and quality
report. Estimates and source-backed entries are reported separately.
