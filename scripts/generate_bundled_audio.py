from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.dictionary import DATA_FILE, default_audio_file, pronunciation_to_speech_text
from pronounceit.audio import aiff_has_audio
from pronounceit.dictionary import PronunciationDictionary, normalize_term
from pronounceit.qa import load_checklist


AUDIO_DIR = ROOT / "audio"


def load_audio_jobs(
    data_file: Path = DATA_FILE,
    high_yield_only: bool = False,
) -> list[tuple[str, str, Path]]:
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    required_terms: set[str] | None = None
    if high_yield_only:
        dictionary = PronunciationDictionary.bundled(data_file=data_file)
        required_terms = {
            normalize_term(str(dictionary.lookup(term).get("term") or term))
            for term in load_checklist()
        }
    jobs: list[tuple[str, str, Path]] = []
    seen_paths: set[Path] = set()
    for item in raw.get("terms", []):
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        if required_terms is not None and normalize_term(term) not in required_terms:
            continue
        speech_text = str(item.get("speechText") or "").strip()
        if not speech_text:
            speech_text = pronunciation_to_speech_text(str(item.get("pronunciation") or ""))
        audio_file = str(item.get("audioFile") or default_audio_file(term))
        relative_path = Path(audio_file)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise SystemExit(f"Unsafe audio path for {term}: {audio_file}")
        output_path = ROOT / relative_path
        if output_path in seen_paths:
            continue
        seen_paths.add(output_path)
        jobs.append((term, speech_text, output_path))
    return jobs


def generate_audio(
    force: bool = False,
    jobs: int = 1,
    high_yield_only: bool = False,
) -> dict[str, int]:
    say = shutil.which("say")
    if not say:
        raise SystemExit("The macOS 'say' command is required to generate bundled audio.")

    AUDIO_DIR.mkdir(exist_ok=True)
    jobs = max(1, jobs)
    results: list[tuple[str, str]] = []

    if jobs == 1:
        results = [
            generate_one_audio_job(job, force)
            for job in load_audio_jobs(high_yield_only=high_yield_only)
        ]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = [
                executor.submit(generate_one_audio_job, job, force)
                for job in load_audio_jobs(high_yield_only=high_yield_only)
            ]
            for future in as_completed(futures):
                results.append(future.result())

    generated = sum(1 for status, _term in results if status == "generated")
    skipped = sum(1 for status, _term in results if status == "skipped")
    failed = [term for status, term in results if status == "failed"]

    if failed:
        raise SystemExit("Failed to generate audio for: " + ", ".join(failed))
    return {"generated": generated, "skipped": skipped, "total": generated + skipped}


def generate_one_audio_job(job: tuple[str, str, Path], force: bool = False) -> tuple[str, str]:
    term, speech_text, output_path = job
    if not speech_text:
        return ("failed", term)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        return ("skipped", term)
    result = subprocess.run(
        ["say", "-o", str(output_path), speech_text],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0 or not aiff_has_audio(output_path):
        return ("failed", term)
    return ("generated", term)


def main() -> None:
    force = "--force" in sys.argv
    high_yield_only = "--high-yield" in sys.argv
    jobs = 1
    if "--jobs" in sys.argv:
        index = sys.argv.index("--jobs")
        try:
            jobs = int(sys.argv[index + 1])
        except (IndexError, ValueError):
            raise SystemExit("--jobs requires a positive integer")
    elif "--parallel" in sys.argv:
        jobs = min(8, os.cpu_count() or 1)

    result = generate_audio(force=force, jobs=jobs, high_yield_only=high_yield_only)
    print(
        f"Bundled audio ready: generated={result['generated']} "
        f"skipped={result['skipped']} total={result['total']}"
    )


if __name__ == "__main__":
    main()
