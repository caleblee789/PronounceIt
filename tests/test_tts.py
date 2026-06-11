import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pronounceit.tts import (
    CompositeTtsEngine,
    GeneratedAudioFileEngine,
    LocalAudioFileEngine,
    TtsEngine,
    TtsResult,
    TtsSettings,
)


class FailingEngine(TtsEngine):
    def speak(self, text: str, settings: TtsSettings) -> bool:
        raise RuntimeError("boom")


class RecordingEngine(TtsEngine):
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str, settings: TtsSettings) -> bool:
        if settings.audio_backend == "local_audio":
            return False
        self.spoken.append(text)
        return True


class UnavailableEngine(TtsEngine):
    name = "unavailable"

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        return TtsResult(False, "backend unavailable")


class TtsTests(unittest.TestCase):
    def test_composite_tts_falls_back_after_engine_error(self) -> None:
        recording = RecordingEngine()
        engine = CompositeTtsEngine([FailingEngine(), recording])

        self.assertTrue(engine.speak("clozapine", TtsSettings()))
        self.assertEqual(recording.spoken, ["clozapine"])

    def test_composite_tts_reports_failure_after_all_engines_fail(self) -> None:
        engine = CompositeTtsEngine([UnavailableEngine()])

        result = engine.speak_result("clozapine", TtsSettings())

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "backend unavailable")
        self.assertEqual(result.attempts, ["unavailable: backend unavailable"])

    def test_composite_tts_reports_empty_speech_text(self) -> None:
        result = CompositeTtsEngine([UnavailableEngine()]).speak_result("  ", TtsSettings())

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "empty speech text")

    def test_local_audio_file_engine_plays_safe_relative_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_file = root / "audio" / "clozapine.aiff"
            audio_file.parent.mkdir()
            audio_file.write_bytes(b"FORM")
            engine = LocalAudioFileEngine(root)

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", return_value="/usr/bin/afplay"),
                patch("pronounceit.tts.subprocess.Popen") as popen,
            ):
                result = engine.speak(
                    "kloh zuh peen",
                    TtsSettings(
                        audio_backend="local_audio_then_tts",
                        audio_file="audio/clozapine.aiff",
                    ),
                )

            self.assertTrue(result)
            popen.assert_called_once_with(["afplay", str(audio_file.resolve())])

    def test_local_audio_file_engine_reports_missing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            engine = LocalAudioFileEngine(Path(tmp))

            result = engine.speak_result(
                "kloh zuh peen",
                TtsSettings(
                    audio_backend="local_audio",
                    audio_file="audio/missing.aiff",
                ),
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "local audio unavailable")

    def test_local_audio_file_engine_rejects_path_escape(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = LocalAudioFileEngine(root)

            with patch("pronounceit.tts.subprocess.Popen") as popen:
                result = engine.speak(
                    "anything",
                    TtsSettings(audio_backend="local_audio_then_tts", audio_file="../outside.aiff"),
                )

            self.assertFalse(result)
            popen.assert_not_called()

    def test_local_audio_file_engine_reports_popen_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_file = root / "audio" / "clozapine.aiff"
            audio_file.parent.mkdir()
            audio_file.write_bytes(b"FORM")
            engine = LocalAudioFileEngine(root)

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", return_value="/usr/bin/afplay"),
                patch("pronounceit.tts.subprocess.Popen", side_effect=OSError("nope")),
            ):
                result = engine.speak_result(
                    "kloh zuh peen",
                    TtsSettings(
                        audio_backend="local_audio_then_tts",
                        audio_file="audio/clozapine.aiff",
                    ),
                )

            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "local audio playback failed to start")

    def test_local_audio_only_does_not_fall_back_to_tts(self) -> None:
        recording = RecordingEngine()
        engine = CompositeTtsEngine([LocalAudioFileEngine(Path("/missing")), recording])

        self.assertFalse(engine.speak("clozapine", TtsSettings(audio_backend="local_audio")))
        self.assertEqual(recording.spoken, [])
        self.assertEqual(
            engine.speak_result("clozapine", TtsSettings(audio_backend="local_audio")).reason,
            "local audio unavailable",
        )

    def test_missing_bundled_audio_falls_back_in_mixed_mode(self) -> None:
        recording = RecordingEngine()
        engine = CompositeTtsEngine([LocalAudioFileEngine(Path("/missing")), recording])

        result = engine.speak_result(
            "clozapine",
            TtsSettings(audio_backend="local_audio_then_tts", audio_file="audio/missing.aiff"),
        )

        self.assertTrue(result.ok)
        self.assertEqual(recording.spoken, ["clozapine"])
        self.assertIn("local-audio-file: local audio unavailable", result.attempts)

    def test_generated_audio_file_engine_creates_and_plays_cached_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = GeneratedAudioFileEngine(root)

            def fake_run(command, text, capture_output):
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"FORM")

                class Result:
                    returncode = 0

                return Result()

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"),
                patch("pronounceit.tts.subprocess.run", side_effect=fake_run) as run,
                patch("pronounceit.tts.subprocess.Popen") as popen,
            ):
                result = engine.speak(
                    "kloh zuh peen",
                    TtsSettings(
                        audio_backend="local_audio_then_tts",
                        term="Clozapine",
                    ),
                )

            self.assertTrue(result)
            self.assertTrue((root / "user_files" / "generated_audio" / "clozapine.aiff").exists())
            run.assert_called_once()
            popen.assert_called_once()

    def test_generated_audio_file_engine_reuses_existing_cached_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cached = root / "user_files" / "generated_audio" / "clozapine.aiff"
            cached.parent.mkdir(parents=True)
            cached.write_bytes(b"FORM")
            engine = GeneratedAudioFileEngine(root)

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", return_value="/usr/bin/afplay"),
                patch("pronounceit.tts.subprocess.run") as run,
                patch("pronounceit.tts.subprocess.Popen") as popen,
            ):
                result = engine.speak(
                    "kloh zuh peen",
                    TtsSettings(audio_backend="local_audio_then_tts", term="Clozapine"),
                )

            self.assertTrue(result)
            run.assert_not_called()
            popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
