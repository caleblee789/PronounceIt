import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.release.publish_audio_pack import release_files


class PublishAudioPackTests(unittest.TestCase):
    def test_release_files_requires_exact_public_asset_set(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in {"pack-manifest.json", "SHA256SUMS"} | {
                f"pronounceit-audio-2-{shard}.zip"
                for shard in "0123456789abcdef"
            }:
                (root / name).write_bytes(b"x")
            self.assertEqual(len(release_files(root)), 18)
            (root / "private.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "exactly the 18"):
                release_files(root)


if __name__ == "__main__":
    unittest.main()
