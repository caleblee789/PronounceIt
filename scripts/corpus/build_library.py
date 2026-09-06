"""Export the two runtime inventories; retain source evidence outside the add-on."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pronounceit.audio_pack import audio_asset_id, file_sha256, manifest_content_sha256, validate_manifest
from pronounceit.written_guides import canonical_terms_sha256
from scripts.corpus.written_sources import audit_written_sources, load_written_guides


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audio_inventory(items: list[dict]) -> dict:
    terms = [{"term": item["term"], **({"aliases": item["aliases"]} if item.get("aliases") else {}),
              "assetId": audio_asset_id(item["term"])} for item in items]
    if len({item["assetId"] for item in terms}) != len(terms):
        raise ValueError("duplicate audio term")
    return {"schemaVersion": 1, "canonicalTermsSha256": canonical_terms_sha256(terms), "terms": terms}


def references(value: object) -> list:
    found = {}
    def visit(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "references" and isinstance(child, list):
                    for reference in child:
                        found[json.dumps(reference, sort_keys=True)] = reference
                else:
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    return list(found.values())


def export_written(items: list[dict], guides: dict[str, dict], directory: Path) -> None:
    identity = canonical_terms_sha256(items)
    write_json(directory / "written_pronunciations.json", {
        "schemaVersion": 3, "canonicalTermsSha256": identity,
        "terms": [{"term": item["term"], "pronunciation": guides[item["term"]]["pronunciation"]} for item in items],
    })
    write_json(directory / "written-pronunciation-sources.json", {
        "schemaVersion": 1, "canonicalTermsSha256": identity,
        "terms": [{"term": item["term"], "references": references(guides[item["term"]])}
                  for item in items if references(guides[item["term"]])],
    })


def bind_release(release: dict, library_path: Path, manifest: dict) -> dict:
    validate_manifest(manifest)
    items = json.loads(library_path.read_text(encoding="utf-8"))["terms"]
    if {item["assetId"]: item["term"] for item in items} != {
        identifier: asset["term"] for identifier, asset in manifest["assets"].items()
    }:
        raise ValueError("audio library does not match the pack inventory")
    return {**release, "schemaVersion": 3, "dictionarySha256": manifest["dictionarySha256"],
            "audioLibrarySha256": file_sha256(library_path),
            "packManifestContentSha256": manifest_content_sha256(manifest),
            "packBytes": manifest["totalBytes"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-source", type=Path, default=ROOT / "quality/pronunciation_sources/audio-v1.3.0.json")
    parser.add_argument("--written-source", type=Path, default=ROOT / "quality/pronunciation_sources/written.json")
    parser.add_argument("--pack-manifest", type=Path, required=True)
    args = parser.parse_args()
    items = json.loads(args.audio_source.read_text(encoding="utf-8"))["terms"]
    manifest = validate_manifest(json.loads(args.pack_manifest.read_text(encoding="utf-8")))
    release = json.loads((ROOT / "data/audio-pack-release.json").read_text(encoding="utf-8"))
    if file_sha256(args.pack_manifest) != release["packManifestSha256"]:
        raise ValueError("manifest differs from the published release")
    if file_sha256(args.audio_source) != manifest["dictionarySha256"]:
        raise ValueError("audio source differs from the published release")
    audit_written_sources(args.written_source, items, ROOT / "data/written-guide-corrections.json")
    guides = load_written_guides(args.written_source, items)
    library = ROOT / "data/audio_pronunciations.json"
    write_json(library, audio_inventory(items))
    export_written(items, guides, ROOT / "data")
    write_json(ROOT / "data/audio-pack-release.json", bind_release(release, library, manifest))
    print(f"Exported {len(items):,} audio pronunciations and {len(guides):,} written pronunciations.")


if __name__ == "__main__":
    main()
