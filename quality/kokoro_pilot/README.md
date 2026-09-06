# Local pronunciation pilot

This is the first milestone of the full pronunciation rebuild: ten candidate
MP3s, readable guides, linked references, and a listening page that saves the
user's decisions. Production dictionary, audio, package, and prior pilot assets
are not modified. No bulk-generation command is provided before pilot approval.

## Run

Use a separate Python 3.10–3.13 environment (this run uses Python 3.12).
Install the adjacent requirements.txt in that environment, then run:

    python scripts/audio/kokoro_pilot.py generate
    python scripts/audio/kokoro_pilot.py verify
    python scripts/audio/kokoro_pilot.py serve

The server defaults to http://127.0.0.1:8766. The current revised listening page
is served on http://127.0.0.1:8768 with --port 8768. It saves review.json beside
the generated clips when the user presses Save review. Partial reviews and
correction notes are supported. Accepted source variants are noted in the references.
The page's references are external links; it does not fetch or redistribute
reference-site audio.

Use --resume to reuse an unchanged run. Use --output-dir with a new directory
after editing phonemes, changing generation code, or changing model/voice/speed.
Existing mismatched or incomplete output is never silently replaced.

## Pronunciation authority

pilot.json contains ARPABET syllables with vowel stress and explicit word
boundaries. The same record deterministically renders the written guide and
Kokoro's phonemes. No spelling-to-sound model is invoked for these ten terms.
The model vocabulary is checked before synthesis, because Kokoro otherwise
silently filters unsupported characters.

The references were consulted on 2026-09-05. These are source-informed
transcriptions awaiting user review, not individually verified recordings.
The choledocholithiasis reference abbreviates the prefix; the prefix retains
the existing curated lexicon reading. Pseudomonas aeruginosa uses a generally
accepted reading; minor differences across references do not require correction.

Pronunciation excerpts are short quotations attributed to their respective
reference publishers. Reference definitions and original recordings are not
included. Kokoro code and weights are Apache-2.0; the pinned model card is
https://huggingface.co/hexgrad/Kokoro-82M/tree/f3ff3571791e39611d31c381e3a41a3af07b4987.
This pilot does not import a Wiktionary-derived bulk corpus.

## Acceptance and provenance

    python scripts/audio/kokoro_pilot.py verify --require-approved

This exits with status 2 while review is incomplete or corrections are
requested. Full-generation approval requires all ten Accept decisions plus
acceptance of the voice. Approval is bound to clip checksums, phonemes, source
specification, dictionary hash, generation code, dependency versions, exact model
revision and hashes, voice, speed, sample rate, and encoding settings.

Generation is local CPU inference with a seed per term. Audio uses 24 kHz mono
MP3 at 48 kbps, with short leading/trailing padding and attenuation only if a
waveform exceeds 0.95 peak. Per-clip metadata records duration, bytes, peak and
RMS. Verification never equates file integrity or pilot approval with full
corpus accuracy or release readiness.

After user approval, the next milestone is the full source-backed/estimated
lexicon pipeline and version 3 pack integration. Estimates remain unverified;
the old Azure method approval is not transferable.

## Listening feedback and audio revision 2

The user rejected the first audio set, identifying clips 2, 3, and 4 as clear
examples and clips 5 and 6 as merely close. The rejection and exact feedback
are saved with the original assets in build/kokoro_pilot/2026-09-05-v2.
The accepted candidates are in build/kokoro_pilot/2026-09-05-v3. The user accepted
all ten clips and the voice on 2026-09-05. Their exact feedback and approval
binding are saved in review.json and acceptance.json beside those clips.

The revision places synthesis stress tokens immediately before vowel nuclei,
matching Kokoro's Misaki convention, instead of before syllable onsets. This is
a sound-input correction; written stress formatting is not the current focus.
Pheochromocytoma now follows the National Cancer Institute's full vowel sequence.
Dysdiadochokinesia uses Farlex's full nee-zee-uh ending and short ki vowel.
The guides are available inside the page's reference details.

All ten revised MP3s were fully decoded and validated, and the six essential
phoneme and approval checks pass. These checks do not establish that the revised
pronunciations sound correct. User listening supplied the acceptance gate for
these ten clips; the remaining library is not individually listening-approved.

The full audio run is now prepared separately. See OVERNIGHT_AUDIO_REBUILD.md
at the project root. It has not been started.
