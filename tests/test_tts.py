import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from pronounceit.tts import (
    AudioPackEngine,
    CommandTtsEngine,
    CompositeTtsEngine,
    GeneratedAudioFileEngine,
    LocalAudioFileEngine,
    QtTextToSpeechEngine,
    TtsEngine,
    TtsResult,
    TtsSettings,
)


def valid_aiff_bytes() -> bytes:
    comm = b"COMM" + (18).to_bytes(4, "big") + b"\x00\x01" + (1).to_bytes(4, "big")
    comm += b"\x00\x10" + b"\x40\x0e\xac\x44\x00\x00\x00\x00\x00\x00"
    sound = b"SSND" + (10).to_bytes(4, "big") + b"\x00" * 8 + b"\x00\x01"
    body = b"AIFF" + comm + sound
    return b"FORM" + len(body).to_bytes(4, "big") + body


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


class ImmediateFailureProcess:
    def wait(self, timeout: float) -> int:
        return 1


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
            audio_file.write_bytes(valid_aiff_bytes())
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
            audio_file.write_bytes(valid_aiff_bytes())
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

    def test_local_audio_file_engine_reports_immediate_nonzero_exit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_file = root / "audio" / "clozapine.aiff"
            audio_file.parent.mkdir()
            audio_file.write_bytes(valid_aiff_bytes())
            engine = LocalAudioFileEngine(root)

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", return_value="/usr/bin/afplay"),
                patch("pronounceit.tts.subprocess.Popen", return_value=ImmediateFailureProcess()),
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
            self.assertIn("exited immediately with status 1", result.attempts[0])

    def test_command_tts_engine_reports_immediate_nonzero_exit(self) -> None:
        engine = CommandTtsEngine()

        with (
            patch("pronounceit.tts.platform.system", return_value="Darwin"),
            patch("pronounceit.tts.shutil.which", return_value="/usr/bin/say"),
            patch("pronounceit.tts.subprocess.Popen", return_value=ImmediateFailureProcess()),
        ):
            result = engine.speak_result("clozapine", TtsSettings())

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "system TTS command failed to start")
        self.assertIn("exited immediately with status 1", result.attempts[0])

    def test_command_tts_engine_reports_live_source(self) -> None:
        engine = CommandTtsEngine()

        with (
            patch("pronounceit.tts.platform.system", return_value="Darwin"),
            patch("pronounceit.tts.shutil.which", return_value="/usr/bin/say"),
            patch("pronounceit.tts.subprocess.Popen"),
        ):
            result = engine.speak_result("clozapine", TtsSettings())

        self.assertTrue(result.ok)
        self.assertEqual(result.audio_source, "computer")

    def test_audio_pack_engine_reports_azure_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_file = root / "user_files" / "audio_cache" / "2" / "asset.mp3"
            audio_file.parent.mkdir(parents=True)
            audio_file.write_bytes(b"pack audio")

            class Manager:
                def resolve(self, term: str):
                    return audio_file if term == "clozapine" else None

            engine = AudioPackEngine(root, Manager())
            with patch.object(
                engine._player,
                "play_path",
                return_value=TtsResult(True, "playing local audio"),
            ):
                result = engine.speak_result(
                    "clozapine",
                    TtsSettings(audio_backend="local_audio_then_tts", term="clozapine"),
                )
                self.assertFalse(engine.speak_result(
                    "custom speech", TtsSettings(audio_backend="local_audio_then_tts", term="clozapine", use_text_override=True)
                ).ok)

        self.assertTrue(result.ok)
        self.assertEqual(result.audio_source, "audio")

    def test_local_audio_only_does_not_fall_back_to_tts(self) -> None:
        recording = RecordingEngine()
        generated = GeneratedAudioFileEngine(Path("/missing"))
        engine = CompositeTtsEngine([LocalAudioFileEngine(Path("/missing")), generated, recording])

        with patch.object(generated, "_generate_audio") as generate:
            self.assertFalse(engine.speak("clozapine", TtsSettings(audio_backend="local_audio")))
            generate.assert_not_called()
        self.assertEqual(recording.spoken, [])
        self.assertEqual(
            engine.speak_result("clozapine", TtsSettings(audio_backend="local_audio")).reason,
            "local audio unavailable",
        )

    def test_missing_audio_falls_back_in_mixed_mode(self) -> None:
        recording = RecordingEngine()
        engine = CompositeTtsEngine([LocalAudioFileEngine(Path("/missing")), recording])

        result = engine.speak_result(
            "clozapine",
            TtsSettings(audio_backend="local_audio_then_tts", audio_file="audio/missing.aiff"),
        )

        self.assertTrue(result.ok)
        self.assertEqual(recording.spoken, ["clozapine"])
        self.assertIn("local-audio-file: local audio unavailable", result.attempts)

    def test_local_audio_then_tts_falls_back_after_immediate_playback_exit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio_file = root / "audio" / "clozapine.aiff"
            audio_file.parent.mkdir()
            audio_file.write_bytes(valid_aiff_bytes())
            recording = RecordingEngine()
            engine = CompositeTtsEngine([LocalAudioFileEngine(root), recording])

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", return_value="/usr/bin/afplay"),
                patch("pronounceit.tts.subprocess.Popen", return_value=ImmediateFailureProcess()),
            ):
                result = engine.speak_result(
                    "clozapine",
                    TtsSettings(
                        audio_backend="local_audio_then_tts",
                        audio_file="audio/clozapine.aiff",
                    ),
                )

        self.assertTrue(result.ok)
        self.assertEqual(recording.spoken, ["clozapine"])
        self.assertIn("local-audio-file: local audio playback failed to start", result.attempts)

    def test_generated_audio_file_engine_creates_and_plays_cached_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = GeneratedAudioFileEngine(root)

            def fake_run(command, text, capture_output):
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(valid_aiff_bytes())

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
            self.assertEqual(len(list((root / "user_files" / "generated_audio").glob("*.aiff"))), 1)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0][-1], "Clozapine")
            popen.assert_called_once()

    def test_generated_audio_respects_explicit_user_text_override(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = GeneratedAudioFileEngine(root)

            def fake_run(command, text, capture_output):
                output_path = Path(command[command.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(valid_aiff_bytes())

                class Result:
                    returncode = 0

                return Result()

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"),
                patch("pronounceit.tts.subprocess.run", side_effect=fake_run) as run,
                patch("pronounceit.tts.subprocess.Popen"),
            ):
                engine.speak("clozapine", TtsSettings(audio_backend="local_audio_then_tts", term="Clozapine"))
                self.assertTrue(
                    engine.speak(
                        "custom clozapine",
                        TtsSettings(
                            audio_backend="local_audio_then_tts",
                            term="Clozapine",
                            use_text_override=True,
                        ),
                    )
                )

            self.assertEqual(run.call_args.args[0][-1], "custom clozapine")
            self.assertEqual(run.call_count, 2)

    def test_generated_audio_file_engine_reuses_existing_cached_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = GeneratedAudioFileEngine(root)

            def fake_run(command, text, capture_output):
                Path(command[command.index("-o") + 1]).write_bytes(valid_aiff_bytes())
                return Mock(returncode=0)

            with (
                patch("pronounceit.tts.platform.system", return_value="Darwin"),
                patch("pronounceit.tts.shutil.which", return_value="/usr/bin/afplay"),
                patch("pronounceit.tts.subprocess.run", side_effect=fake_run) as run,
                patch("pronounceit.tts.subprocess.Popen") as popen,
            ):
                result = engine.speak_result(
                    "kloh zuh peen",
                    TtsSettings(audio_backend="local_audio_then_tts", term="Clozapine"),
                )
                engine.speak_result("kloh zuh peen", TtsSettings(audio_backend="local_audio_then_tts", term="Clozapine"))
                self.assertEqual(run.call_count, 1)
                engine.speak_result("kloh zuh peen", TtsSettings(audio_backend="local_audio_then_tts", term="Clozapine", voice="Samantha"))
                engine.speak_result("kloh zuh peen", TtsSettings(audio_backend="local_audio_then_tts", term="Clozapine", voice="Samantha", rate=2))

            self.assertTrue(result.ok)
            self.assertEqual(result.audio_source, "computer")
            self.assertEqual(run.call_count, 3)
            self.assertIn("Samantha", run.call_args.args[0])
            self.assertIn("216", run.call_args.args[0])
            self.assertEqual(popen.call_count, 4)

    def test_qt_voice_and_rate_return_to_default(self) -> None:
        engine = QtTextToSpeechEngine()
        engine._engine = Mock()
        default = Mock()
        voice = Mock()
        voice.name.return_value = "Samantha"
        engine._default_voice = default
        engine._engine.availableVoices.return_value = [voice]
        self.assertTrue(engine.speak("test", TtsSettings(voice="Samantha", rate=4)))
        engine._engine.setVoice.assert_called_with(voice)
        engine._engine.setRate.assert_called_with(0.4)
        self.assertTrue(engine.speak("test", TtsSettings()))
        engine._engine.setVoice.assert_called_with(default)
        engine._engine.setRate.assert_called_with(0)


if __name__ == "__main__":
    unittest.main()
