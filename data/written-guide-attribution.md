# Written pronunciation sources

PronounceIt converts selected dictionary pronunciations to readable respelling. It prefers US English, then unmarked English, then other standard English variants. One variant is displayed. Hyphens divide readable sound groups; capitals mark primary stress. Long guides may wrap.

The text data is independent of audio. Published references take priority. Remaining entries use generated estimates. Exact methods, source phonetics, and review records are preserved in the repository under quality/pronunciation_sources/written.json, separately from the compact runtime inventories. The interface shows the same pronunciation field for every entry. Composed phrases preserve their individual source or generation records.

## Wiktionary contributors

Primary source: English Wiktionary, dump dated 2026-08-05, extracted by Wiktextract on 2026-08-28 (revision 872fc7b), distributed by https://kaikki.org/dictionary/rawdata.html.

Wiktionary-derived entries and their adapted respellings in written_pronunciations.json are available under Creative Commons Attribution-ShareAlike 4.0: https://creativecommons.org/licenses/by-sa/4.0/. Their per-entry references in written-pronunciation-sources.json link to the original articles and contributor histories. Source IPA, selected accent tags, dump date, and extraction line are retained in the repository source records. Changes consist of pronunciation selection, conversion to respelling, and, where indicated, composition of referenced words. No endorsement by the original contributors is implied.

## CMUdict

Secondary source: Carnegie Mellon University Speech Group, CMU Pronouncing Dictionary, revision 74790861f652b15e4ac49015a90074ad62a27690: https://github.com/cmusphinx/cmudict.

See written-guide-CMUdict-LICENSE.txt for its copyright notice, redistribution terms, and disclaimer. Original ARPABET and the selected variant are recorded in the repository source evidence.

## Documented corrections and reproducibility

The supplemental pass uses the National Cancer Institute's Dictionary of Cancer Terms, retrieved September 6, 2026, and Grady Ward's Moby Pronunciator II. These fill entries unresolved by the primary pass. NCI supplies readable pronunciation keys; only complete keys without ellipses are used. The original keys and per-term NCI links are retained. NCI text may be reused with attribution unless otherwise indicated: https://www.cancer.gov/policies/copyright-reuse. These pronunciation keys were originally published by the National Cancer Institute; no NCI endorsement is implied.

Grady Ward dedicated the Moby documentation and database to the public domain in January 2001. Its ASCII phonetic data is converted using the documented phone set; unknown symbols are rejected. The Moby source can be obtained at https://www.gutenberg.org/ebooks/3205. The original source download and its license are retained with the build snapshots. Per-record provenance identifies the exact source line and transcription. Moby is a historical general-English reference; its entries are source-backed, not individually clinically verified. The two supplemental snapshots are checksummed in the data manifest.

Documented corrections cite their individual references in data/written-guide-corrections.json in the repository; selected references are included in written-pronunciation-sources.json. These are independently written short pronunciation guides, not imported dictionary definitions. They fill gaps or, when explicitly marked, correct an identified error in a selected source. Only corrections actually selected by the builder appear in the runtime data.

## Generation for remaining terms

The gap-filling process uses Misaki 0.9.4's US gold/silver lexicons as estimates, AI-authored medical combining forms and clinical guides, reference-based inflection/prefix analogies, and eSpeak NG's US English word rules. Misaki data is adapted from https://github.com/hexgrad/misaki under Apache 2.0; its license accompanies the add-on in written-guide-Misaki-LICENSE.txt. Converted symbols and stress are retained in each generated record. Misaki is not presented as a medical dictionary. The local eSpeak engine and generation dependencies are not distributed in the add-on. See https://github.com/espeak-ng/espeak-ng for the engine source.

Generated analogies derived from Wiktionary phonetics remain adaptations under CC BY-SA 4.0 and preserve the source record and URL in their base provenance. Generated phrase records retain each component's provenance. No source publisher or tool author endorses these guides. AI-authored corrections and medical word-part rules are estimates, not individual human clinical review. Full-library linguistic accuracy has not been measured.

The repository source manifest records source checksums, canonical terms and aliases, builder and converter checksums, the corrections checksum, and generation tools, versions, inputs, and checksums. The application code remains MIT licensed; the source-data terms above apply separately. Source licensing does not describe or change the separately generated audio.
