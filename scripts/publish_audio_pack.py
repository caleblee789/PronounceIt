from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_audio_pack import DEFAULT_OUTPUT_DIR, verify_pack


DEFAULT_REPOSITORY = "caleblee789/PronounceIt"
DEFAULT_TAG = "audio-pack-v2"


def release_files(directory: Path) -> list[Path]:
    expected = {"pack-manifest.json", "SHA256SUMS"} | {
        f"pronounceit-audio-2-{shard}.zip" for shard in "0123456789abcdef"
    }
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    if actual != expected:
        raise SystemExit(
            "Audio release directory must contain exactly the 18 public artifacts: "
            f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    return [directory / "pack-manifest.json", directory / "SHA256SUMS"] + [
        directory / f"pronounceit-audio-2-{shard}.zip"
        for shard in "0123456789abcdef"
    ]


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def assert_clean_checkout() -> None:
    tracked = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if tracked:
        raise SystemExit("Refusing to publish from a checkout with uncommitted tracked changes.")


def publish(
    files: list[Path],
    repository: str,
    tag: str,
    target: str,
) -> dict[str, object]:
    run_checked(["gh", "auth", "status", "-h", "github.com"])
    assert_clean_checkout()
    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository],
        text=True,
        capture_output=True,
    )
    if existing.returncode == 0:
        raise SystemExit(f"Refusing to overwrite existing GitHub Release: {tag}")
    if "release not found" not in (existing.stderr + existing.stdout).casefold():
        raise SystemExit(f"Could not confirm that release {tag} is absent: {existing.stderr.strip()}")

    notes = (
        "First public PronounceIt comprehensive audio pack.\n\n"
        "Contains 95,902 checksum-verified MP3 assets in 16 deterministic shards. "
        "Install it from PronounceIt Settings; do not extract these files manually."
    )
    run_checked(
        [
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            repository,
            "--target",
            target,
            "--title",
            "PronounceIt Audio Pack 2",
            "--notes",
            notes,
            "--latest=false",
            *[str(path) for path in files],
        ]
    )
    result = json.loads(
        run_checked(
            [
                "gh",
                "release",
                "view",
                tag,
                "--repo",
                repository,
                "--json",
                "assets,isDraft,isPrerelease,tagName,url",
            ]
        ).stdout
    )
    assets = {item["name"]: int(item["size"]) for item in result.get("assets", [])}
    expected = {path.name: path.stat().st_size for path in files}
    if assets != expected or result.get("isDraft") or result.get("isPrerelease"):
        raise SystemExit("Published GitHub Release does not match the verified local artifacts.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and publish the audio-pack release.")
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--target", default="main")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    summary = verify_pack(output_dir=args.artifacts)
    files = release_files(args.artifacts)
    output: dict[str, object] = {
        **summary,
        "releaseFiles": len(files),
        "releaseBytes": sum(path.stat().st_size for path in files),
        "publishRequested": args.publish,
    }
    if args.publish:
        output["release"] = publish(files, args.repo, args.tag, args.target)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
