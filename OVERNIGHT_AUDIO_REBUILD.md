# Overnight audio rebuild

The full run is prepared and has not been started.

When ready, open the PronounceIt folder in Finder and double-click
**Start Overnight Audio Rebuild.command**. Keep your Mac plugged in with the lid
open. You can minimize its Terminal window. The launcher keeps the Mac awake
while the rebuild is running; the display can turn off normally.

Allow roughly **12–14 hours**, including validation and packaging. This remains
an estimate, and the live progress updates will refine it. The job uses four CPU
threads at reduced priority. The bounded preflight used about **2 GB of memory**.
It will use noticeable CPU, so warmth and fan activity are expected. All sources,
model files, and dependencies are already local; no paid service or internet
connection is needed for the run.

The job automatically generates all 95,902 clips, checks playback and checksums,
replaces the 155 bundled recordings in a separate candidate, builds the 16
download files, and writes a matching add-on package and quality report. The
written guides and aliases are preserved. The current release stays available.

**To stop:** press Control-C in the Terminal window. Double-click the same
launcher again to resume. Completed clips are reused only when their inputs,
voice settings, and checksums still match. A second launch cannot start a
competing rebuild.

**Progress:** `build/kokoro-rebuild/overnight.log` and
`build/kokoro-rebuild/run-2026-09-05/progress.json`.

**Finished files:**
`build/kokoro-rebuild/run-2026-09-05/release-candidate/`.
Look for `READ-ME-FIRST.md`, `quality-report.json`, the `.ankiaddon` file, and
the `audio-pack` folder.

Leave the prepared generation files and project source unchanged during the
run. The launcher checks their identities and stops if they change. It also
checks free space and preserves completed output if a problem occurs. Keep at
least 8 GiB free before starting.

The ten pilot clips and voice were accepted. That approval does not establish
an accuracy rate for the whole library. The quality report separates those ten
clips, 15,922 other reference-backed inputs, and 79,970 unverified estimates.
Four incomplete source name fragments are spoken as letter names and explicitly
flagged for follow-up. Minor accepted variants are recorded without blocking
the rebuild.

The finished candidate still needs the planned disposable-Anki checks and a
release review. This launcher does not publish or install the new release.
