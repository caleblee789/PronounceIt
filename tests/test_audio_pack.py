import hashlib
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pronounceit.audio_pack import (
    AudioPackManager,
    audio_asset_id,
    dictionary_sha256,
    file_sha256,
    validate_manifest,
)


def valid_mp3_bytes() -> bytes:
    frame = b"\xff\xfb\x90\x64" + (b"\x00" * 413)
    return frame * 10


class AudioPackTests(unittest.TestCase):
    def test_manifest_url_can_be_overridden_for_isolated_validation(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"PRONOUNCEIT_AUDIO_PACK_MANIFEST_URL": "http://127.0.0.1:8765/pack-manifest.json"},
        ):
            manager = AudioPackManager(Path(tmp))
            self.assertEqual(
                manager.manifest_url,
                "http://127.0.0.1:8765/pack-manifest.json",
            )

    def test_candidate_uses_its_matching_pack_address_and_keeps_explicit_override(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PRONOUNCEIT_AUDIO_PACK_MANIFEST_URL": ""}):
            root = Path(tmp)
            (root / "data").mkdir()
            url = "https://example.com/audio-pack-v3/pack-manifest.json"
            (root / "data/audio-pack-release.json").write_text(json.dumps({"schemaVersion": 3, "manifestUrl": url}))
            self.assertEqual(AudioPackManager(root).manifest_url, url)
            self.assertEqual(AudioPackManager(root, manifest_url="http://127.0.0.1/pack.json").manifest_url,
                             "http://127.0.0.1/pack.json")

    def test_download_rejects_insufficient_free_space_before_fetching_shards(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            dictionary = root / "data" / "medical_pronunciations.json"
            dictionary.write_text('{"terms": []}\n', encoding="utf-8")
            manager = AudioPackManager(root)
            manifest = {
                "schemaVersion": 2,
                "packVersion": "2-test",
                "dictionarySha256": dictionary_sha256(dictionary),
                "reviewLedgerSha256": "1" * 64,
                "synthesisStrategyCounts": {"azure-native": 1, "manual-sapi": 0},
                "shards": [
                    {
                        "id": shard_id,
                        "file": f"shard-{shard_id}.zip",
                        "sha256": "2" * 64,
                        "size": 1024,
                    }
                    for shard_id in "0123456789abcdef"
                ],
            }
            manager._fetch_manifest = lambda: manifest
            with patch("pronounceit.audio_pack.shutil.disk_usage") as disk_usage:
                disk_usage.return_value = type("Usage", (), {"free": 1})()
                with self.assertRaisesRegex(Exception, "not enough free disk space"):
                    manager.download()

    def test_asset_ids_are_normalized_and_collision_resistant(self) -> None:
        self.assertEqual(audio_asset_id(" Clozapine. "), audio_asset_id("clozapine"))
        self.assertNotEqual(audio_asset_id("clozapine"), audio_asset_id("quetiapine"))

    def test_manifest_requires_exactly_sixteen_shards(self) -> None:
        with self.assertRaisesRegex(Exception, "all 16 shards"):
            validate_manifest(
                {
                    "schemaVersion": 2,
                    "packVersion": "2-test",
                    "dictionarySha256": "0" * 64,
                    "reviewLedgerSha256": "1" * 64,
                    "synthesisStrategyCounts": {"azure-native": 1, "manual-sapi": 0},
                    "shards": [],
                }
            )

    def test_manifest_rejects_generated_g2p_strategy(self) -> None:
        with self.assertRaisesRegex(Exception, "forbidden synthesis strategy"):
            validate_manifest(
                {
                    "schemaVersion": 2,
                    "packVersion": "2",
                    "dictionarySha256": "0" * 64,
                    "reviewLedgerSha256": "1" * 64,
                    "synthesisStrategyCounts": {"generated-g2p": 1},
                    "shards": [],
                }
            )

    def test_manager_resolves_audio_from_installed_shard_and_cache(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            dictionary = data_dir / "medical_pronunciations.json"
            dictionary.write_text('{"terms": []}\n', encoding="utf-8")
            manager = AudioPackManager(root, cache_bytes=1024 * 1024)
            version_dir = manager.pack_root / "2-test"
            version_dir.mkdir(parents=True)
            term = "clozapine"
            asset_id = audio_asset_id(term)
            shards = []
            for shard_id in "0123456789abcdef":
                shard_path = version_dir / f"shard-{shard_id}.zip"
                with zipfile.ZipFile(shard_path, "w", compression=zipfile.ZIP_STORED) as archive:
                    if shard_id == asset_id[0]:
                        archive.writestr(f"audio/{asset_id}.mp3", valid_mp3_bytes())
                    else:
                        archive.writestr("empty.txt", shard_id)
                shards.append(
                    {
                        "id": shard_id,
                        "file": shard_path.name,
                        "sha256": file_sha256(shard_path),
                        "size": shard_path.stat().st_size,
                        "assetCount": int(shard_id == asset_id[0]),
                    }
                )
            manifest = {
                "schemaVersion": 2,
                "packVersion": "2-test",
                "dictionarySha256": dictionary_sha256(dictionary),
                "reviewLedgerSha256": "1" * 64,
                "synthesisStrategyCounts": {"azure-native": 1, "manual-sapi": 0},
                "assetCount": 1,
                "shards": shards,
            }
            (version_dir / "pack-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            manager.pack_root.mkdir(parents=True, exist_ok=True)
            manager.state_path.write_text('{"packVersion":"2-test"}', encoding="utf-8")

            self.assertTrue(manager.status(verify_hashes=True).installed)
            resolved = manager.resolve(term)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.read_bytes(), valid_mp3_bytes())
            self.assertEqual(manager.resolve(term), resolved)

    def test_unknown_local_state_is_treated_as_not_installed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "medical_pronunciations.json").write_text(
                '{"terms": []}\n', encoding="utf-8"
            )
            manager = AudioPackManager(root)
            manager.pack_root.mkdir(parents=True)
            manager.state_path.write_text('{"packVersion":"experimental"}', encoding="utf-8")
            (manager.pack_root / "experimental").mkdir()
            status = manager.status()
            self.assertFalse(status.installed)
            self.assertEqual(status.message, "Offline pronunciation pack is not installed.")
            manager.remove()
            self.assertFalse(manager.state_path.exists())

    def test_partial_download_manifest_is_discovered_after_restart(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            dictionary = data_dir / "medical_pronunciations.json"
            dictionary.write_text('{"terms": []}\n', encoding="utf-8")
            manager = AudioPackManager(root)
            version_dir = manager.pack_root / "2-test"
            version_dir.mkdir(parents=True)

            shards = []
            for shard_id in "0123456789abcdef":
                shard_path = version_dir / f"shard-{shard_id}.zip"
                if shard_id == "0":
                    shard_path.write_bytes(b"complete shard")
                shards.append(
                    {
                        "id": shard_id,
                        "file": shard_path.name,
                        "sha256": file_sha256(shard_path) if shard_path.exists() else "0" * 64,
                        "size": shard_path.stat().st_size if shard_path.exists() else 1,
                    }
                )
            manifest = {
                "schemaVersion": 2,
                "packVersion": "2-test",
                "dictionarySha256": dictionary_sha256(dictionary),
                "reviewLedgerSha256": "1" * 64,
                "synthesisStrategyCounts": {"azure-native": 1, "manual-sapi": 0},
                "shards": shards,
            }
            (version_dir / "pack-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            status = manager.status()
            self.assertFalse(status.installed)
            self.assertEqual((status.downloaded_shards, status.total_shards), (1, 16))
            self.assertEqual(status.message, "Offline pronunciation pack download is incomplete (1/16 files).")


if __name__ == "__main__":
    unittest.main()
