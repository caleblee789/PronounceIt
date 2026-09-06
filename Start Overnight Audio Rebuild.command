#!/bin/zsh
# Double-click this file in Finder when ready. --check never starts synthesis.
set -u
set -o pipefail
rebuild_root="${0:A:h}"
cd -- "$rebuild_root" || exit 1
rebuild_python="$rebuild_root/.venv-generation/bin/python"
rebuild_script="$rebuild_root/scripts/audio/kokoro_rebuild.py"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4

if [[ ! -x "$rebuild_python" ]]; then
  print "The prepared pronunciation environment is missing. Ask Codex to repair it before starting."
  exit 1
fi
if [[ "${1:-}" == "--check" ]]; then
  exec "$rebuild_python" "$rebuild_script" ready
fi
if [[ "$#" != 0 ]]; then
  print "Use this launcher without arguments to start, or --check to check readiness only."
  exit 2
fi

mkdir -p "$rebuild_root/build/kokoro-rebuild"
rebuild_log="$rebuild_root/build/kokoro-rebuild/overnight.log"
print "PronounceIt overnight audio rebuild"
print "Keep this Mac plugged in with its lid open. This window can be minimized."
print "Control-C stops safely; double-click this launcher again to resume."
print "Progress is saved in build/kokoro-rebuild/overnight.log."
print "Started: $(date)" >> "$rebuild_log"
/usr/bin/caffeinate -i "$rebuild_python" -W ignore::FutureWarning "$rebuild_script" run 2>&1 | /usr/bin/tee -a "$rebuild_log"
rebuild_result=$pipestatus[1]
if [[ "$rebuild_result" == 0 ]]; then
  print "Finished. The matching add-on, download pack, and quality report are saved in:"
  print "$rebuild_root/build/kokoro-rebuild/run-2026-09-05/release-candidate"
else
  print "The rebuild stopped. Completed clips are saved. See the last message in the progress log."
fi
if [[ -t 0 ]]; then
  read -r "rebuild_reply?Press Return to close this window. "
fi
exit "$rebuild_result"
