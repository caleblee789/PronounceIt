"""Offline regression checks for resumable output and matching v3 packs."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from pronounceit.audio_pack import AudioPackManager, audio_asset_id, validate_manifest
from scripts.audio.kokoro_pilot import atomic_json
from scripts.audio.kokoro_rebuild import ensure_asset
from scripts.audio.kokoro_pack import candidate_dictionary, write_pack
from tests.test_audio_pack import valid_mp3_bytes


def record(term: str) -> dict:
    return {"term": term, "assetId": audio_asset_id(term), "phonemes": "tˈɛst", "phonemeInputSha256": "1" * 64,
            "aliases": ["sample alias"], "words": [{"text": term, "phonemes": "tˈɛst", "provenance": {"kind": "estimate"}}],
            "reviewStatus": "unverified-estimate", "clipReviewStatus": "unreviewed"}


class RebuildTests(unittest.TestCase):
    @patch("scripts.audio.kokoro_rebuild.validate_decoding")
    def test_resume_recovers_interrupted_commit_and_rejects_stale_or_corrupt_audio(self, _decoder) -> None:
        with TemporaryDirectory() as tmp:
            directory, item = Path(tmp), record("test")
            synthesize = Mock(return_value=valid_mp3_bytes())
            expected = ensure_asset(item, directory, "a" * 64, synthesize)
            identifier = item["assetId"]
            (directory / f"{identifier}.meta.json").rename(directory / f"{identifier}.pending.json")
            (directory / f"{identifier}.mp3").rename(directory / f"{identifier}.mp3.tmp")
            self.assertEqual(ensure_asset(item, directory, "a" * 64, synthesize), expected)
            self.assertEqual(ensure_asset(item, directory, "a" * 64, synthesize), expected)
            synthesize.assert_called_once()
            changed = {**item, "phonemes": "different"}
            with self.assertRaisesRegex(ValueError, "Stale"):
                ensure_asset(changed, directory, "a" * 64, synthesize)
            path = directory / f"{identifier}.mp3"
            path.write_bytes(path.read_bytes()[:-1] + b"x")
            with self.assertRaisesRegex(ValueError, "Changed"):
                ensure_asset(item, directory, "a" * 64, synthesize)

    @patch("scripts.audio.kokoro_rebuild.validate_decoding")
    def test_candidate_pack_download_restart_cache_and_provider_metadata(self, _decoder) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [record("test")]
            reports = {records[0]["assetId"]: ensure_asset(records[0], root / "audio", "a" * 64, lambda *_: valid_mp3_bytes())}
            generation = {"provider": "kokoro-local", "model": "hexgrad/Kokoro-82M", "modelRevision": "revision",
                          "voice": "af_heart", "speed": 0.95, "bindingSha256": "a" * 64}
            original = {"terms": [{"term": "test", "pronunciation": "TEST", "syllables": "test", "aliases": ["sample alias"]}]}
            dictionary = candidate_dictionary(original, records, reports, {"test"}, generation)
            self.assertEqual(dictionary["terms"][0]["pronunciation"], "TEST")
            self.assertEqual(dictionary["terms"][0]["audioReviewStatus"], "unreviewed")
            target = root / "addon/data/medical_pronunciations.json"
            target.parent.mkdir(parents=True)
            atomic_json(target, dictionary)
            manifest = write_pack(root / "pack", target, root / "audio", records, reports, generation,
                                  {"recordsSha256": "2" * 64}, {"bindingSha256": "3" * 64})
            manager = AudioPackManager(root / "addon", manifest_url=(root / "pack/pack-manifest.json").as_uri())
            self.assertTrue(manager.download().installed)
            cached = manager.resolve("test")
            self.assertEqual(cached.read_bytes(), valid_mp3_bytes())
            cached.write_bytes(valid_mp3_bytes()[:-1] + b"x")
            self.assertEqual(manager.resolve("test").read_bytes(), valid_mp3_bytes())
            restarted = AudioPackManager(root / "addon")
            self.assertEqual(restarted.resolve("test"), cached)
            self.assertEqual(restarted.playback_metadata("test")["source"], "recorded")
            self.assertEqual(restarted.playback_metadata("test")["reviewStatus"], "unreviewed")
            changed = deepcopy(manifest)
            changed["review"]["methodApproval"] = "azure-approved"
            with self.assertRaisesRegex(Exception, "approval"):
                validate_manifest(changed)
            target.write_text(target.read_text() + " ")
            self.assertIsNone(restarted.resolve("test"))


if __name__ == "__main__":
    unittest.main()
