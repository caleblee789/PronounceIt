import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pronounceit.audio_pack import audio_asset_id, dictionary_sha256, file_sha256, validate_manifest
from pronounceit.audio_review import method_binding_sha256
from scripts.audio.build_audio_pack import build_pack, validate_release_reviews
from scripts.audio.generate_neural_audio import _metadata, build_jobs, build_pilot_binding


def valid_mp3_bytes() -> bytes:
    frame = b"\xff\xfb\x90\x64" + (b"\x00" * 413)
    return frame * 10


def write_complete_generation(data_file: Path, audio_dir: Path) -> tuple[list[dict], Path]:
    audio_dir.mkdir()
    reports: list[dict] = []
    for job in build_jobs(data_file, audio_dir):
        data = valid_mp3_bytes()
        job.output_path.write_bytes(data)
        metadata = _metadata(job, data)
        job.output_path.with_suffix(".meta.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        reports.append(
            {
                "term": job.term,
                "assetId": job.asset_id,
                "sha256": metadata["audioSha256"],
                "bytes": metadata["bytes"],
                "durationMs": metadata["durationMs"],
                "synthesisStrategy": job.synthesis_strategy,
                "audioReviewStatus": "method-approved",
                "ssmlSha256": job.ssml_sha256,
            }
        )
    (audio_dir / "generation-report.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in reports), encoding="utf-8"
    )
    binding = build_pilot_binding(data_file, audio_dir)
    ledger_path = audio_dir.parent / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "packVersion": "2",
                "entries": [],
                "methodApproval": {
                    "status": "method-approved",
                    "scope": "synthesis-method",
                    "reviewer": "test",
                    "statement": "Approved test method.",
                    "binding": binding,
                    "bindingSha256": method_binding_sha256(binding),
                },
            }
        ),
        encoding="utf-8",
    )
    (audio_dir / "build-manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "dictionarySha256": dictionary_sha256(data_file),
                "reviewLedgerSha256": file_sha256(ledger_path),
            }
        ),
        encoding="utf-8",
    )
    return reports, ledger_path


class BuildAudioPackTests(unittest.TestCase):
    def test_release_gate_rejects_generated_g2p_and_unreviewed_audio(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "dictionary.json"
            data_file.write_text(
                json.dumps(
                    {
                        "terms": [
                            {
                                "term": "clozapine",
                                "pronunciation": "KLOH-zuh-peen",
                                "syllables": "clo-za-pine",
                                "source": "generated-g2p-en",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            audio_dir = root / "audio"
            reports, ledger = write_complete_generation(data_file, audio_dir)
            reports[0].update(
                {"synthesisStrategy": "generated-g2p", "phonemes": ["legacy"]}
            )
            (audio_dir / "generation-report.jsonl").write_text(
                json.dumps(reports[0]) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "review gate failed"):
                validate_release_reviews(data_file, audio_dir, ledger)

    def test_build_pack_creates_sixteen_valid_checksum_shards(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "dictionary.json"
            data_file.write_text(
                json.dumps(
                    {
                        "terms": [
                            {"term": "clozapine", "pronunciation": "KLOH-zuh-peen", "syllables": "clo-za-pine"},
                            {"term": "quetiapine", "pronunciation": "kweh-TYE-uh-peen", "syllables": "que-ti-a-pine"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            audio_dir = root / "audio"
            _reports, ledger_path = write_complete_generation(data_file, audio_dir)

            manifest = build_pack(
                data_file=data_file,
                audio_dir=audio_dir,
                output_dir=root / "pack",
                pack_version="2-test",
                base_url="https://example.invalid/audio",
                review_ledger_path=ledger_path,
            )

            self.assertEqual(manifest["assetCount"], 2)
            self.assertEqual(len(manifest["shards"]), 16)
            self.assertEqual(sum(item["assetCount"] for item in manifest["shards"]), 2)
            self.assertEqual(validate_manifest(manifest), manifest)
            self.assertTrue(all((root / "pack" / item["file"]).is_file() for item in manifest["shards"]))
            self.assertTrue((root / "pack" / "SHA256SUMS").is_file())
            first_sums = (root / "pack" / "SHA256SUMS").read_text(encoding="utf-8")
            build_pack(
                data_file=data_file,
                audio_dir=audio_dir,
                output_dir=root / "pack",
                pack_version="2-test",
                base_url="https://example.invalid/audio",
                review_ledger_path=ledger_path,
            )
            self.assertEqual(
                (root / "pack" / "SHA256SUMS").read_text(encoding="utf-8"),
                first_sums,
            )


if __name__ == "__main__":
    unittest.main()
