import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pronounceit.audio_pack import audio_asset_id
from scripts.generate_neural_audio import _job_batches, build_jobs, generate


class NeuralAudioGenerationTests(unittest.TestCase):
    def test_build_jobs_creates_fluent_ssml_and_deterministic_asset(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "data.json"
            data_file.write_text(
                '{"terms":[{"term":"clozapine","pronunciation":"KLOH-zuh-peen","syllables":"clo-za-pine"}]}',
                encoding="utf-8",
            )

            jobs = build_jobs(data_file=data_file, output_dir=root / "audio")

            self.assertEqual(len(jobs), 1)
            self.assertNotIn('<phoneme alphabet="sapi"', jobs[0].ssml)
            self.assertIn(">clozapine</prosody>", jobs[0].ssml)
            self.assertEqual(jobs[0].synthesis_strategy, "azure-native")
            self.assertNotIn("kloh zuh peen", jobs[0].ssml)
            self.assertTrue(jobs[0].output_path.name.endswith(".mp3"))
            legacy_id = __import__("hashlib").sha256(b"clozapine").hexdigest()
            self.assertEqual(jobs[0].asset_id, audio_asset_id("clozapine"))
            self.assertNotEqual(jobs[0].asset_id, legacy_id)

    def test_build_jobs_uses_reviewed_single_and_multiword_sapi(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "data.json"
            data_file.write_text(
                '{"terms":['
                '{"term":"clozapine","pronunciation":"KLOH-zuh-peen","syllables":"clo-za-pine","sapiPhonemes":"k l ow 1 - z ax - p iy 2 n"},'
                '{"term":"test phrase","pronunciation":"TEST FRAYZ","syllables":"test phrase","sapiSegments":[{"text":"test","sapi":"t eh 1 s t"},{"text":"phrase","sapi":"f r ey 1 z"}]}'
                ']}',
                encoding="utf-8",
            )
            jobs = build_jobs(data_file, root / "audio")
            self.assertEqual([job.synthesis_strategy for job in jobs], ["manual-sapi", "manual-sapi"])
            self.assertEqual(sum('<phoneme alphabet="sapi"' in job.ssml for job in jobs), 2)
            self.assertIn(">test</phoneme> <phoneme", jobs[1].ssml)

    def test_generate_uses_batch_client_and_writes_valid_resumable_audio(self) -> None:
        class FakeBatchClient:
            def __init__(self) -> None:
                self.calls = 0

            def synthesize_batch(self, jobs):
                self.calls += 1
                frame = b"\xff\xfb\x90\x64" + (b"\x00" * 413)
                return [frame * 10 for _job in jobs]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "data.json"
            data_file.write_text(
                '{"terms":[{"term":"clozapine","pronunciation":"KLOH-zuh-peen","syllables":"clo-za-pine"}]}',
                encoding="utf-8",
            )
            jobs = build_jobs(data_file, root / "audio")
            client = FakeBatchClient()

            first = generate(jobs, client, workers=1)
            second = generate(jobs, client, workers=1)

            self.assertEqual(first[0]["status"], "generated")
            self.assertGreater(first[0]["durationMs"], 200)
            self.assertEqual(second[0]["status"], "skipped")
            self.assertEqual(client.calls, 1)

            data_file.write_text(
                '{"terms":[{"term":"clozapine","pronunciation":"KLOH-zuh-peen",'
                '"syllables":"clo-za-pine","sapiPhonemes":"k l ow 1 - z ax - p iy 2 n"}]}',
                encoding="utf-8",
            )
            corrected_jobs = build_jobs(data_file, root / "audio")
            corrected = generate(corrected_jobs, client, workers=1)
            self.assertEqual(corrected[0]["status"], "generated")
            self.assertEqual(client.calls, 2)

    def test_job_batches_respect_azure_payload_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_file = root / "data.json"
            data_file.write_text(
                '{"terms":[{"term":"test","pronunciation":"TEST","syllables":"test"}]}',
                encoding="utf-8",
            )
            job = build_jobs(data_file, root / "audio")[0]
            batches = _job_batches([job] * 20_000)

            self.assertGreaterEqual(len(batches), 2)
            self.assertTrue(all(len(batch) <= 10_000 for batch in batches))


if __name__ == "__main__":
    unittest.main()
