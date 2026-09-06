"""Download free supplemental references once; keep checksummed local snapshots."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import string
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MOBY_URL = "https://www.gutenberg.org/files/3205/files.zip"
NCI_BASE = "https://webapis.cancer.gov/glossary/v1/Terms/expand/Cancer.gov/Patient/en/"


def fetch(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    lock_path = output / "sources.lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        for name, record in lock["files"].items():
            if hashlib.sha256((output / name).read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError(f"Changed supplemental snapshot: {name}")
        print("Using intact supplemental snapshots")
        return

    def download(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "PronounceIt-reference-import/1"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read()

    archive_bytes = download(MOBY_URL)
    (output / "moby-pronunciator.zip").write_bytes(archive_bytes)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        (output / "mpron.txt").write_bytes(archive.read("mpron.txt"))
    urls, terms = [], []
    for letter in string.ascii_uppercase + "#":
        url = NCI_BASE + urllib.parse.quote(letter, safe="") + "?size=10000"
        data = json.loads(download(url))
        batch = data["results"]
        if data["meta"]["totalResults"] != len(batch):
            raise ValueError(f"Incomplete NCI response: {letter}")
        urls.append(url)
        terms.extend(batch)
        print(f"NCI {letter}: {len(batch)} entries", flush=True)
    (output / "nci-terms.json").write_text(json.dumps(terms, ensure_ascii=False, separators=(",", ":")) + "\n")
    lock = {"retrievedAt": datetime.now(timezone.utc).isoformat(), "files": {}}
    for name, source_urls in (("mpron.txt", [MOBY_URL]), ("nci-terms.json", urls)):
        lock["files"][name] = {"sha256": hashlib.sha256((output / name).read_bytes()).hexdigest(), "urls": source_urls}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/written-guide-sources")
    fetch(parser.parse_args().output)
