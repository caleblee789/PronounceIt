from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from typing import Any

from .audio import audio_file_has_content
from .audio_pack import AudioPackManager


AudioBackend = Literal["system_tts", "local_audio", "local_audio_then_tts"]
AudioSource = Literal["custom", "azure", "generated", "live"]


@dataclass(frozen=True)
class TtsSettings:
    voice: str = ""
    rate: int = 0
    volume: int = 100
    audio_backend: AudioBackend = "system_tts"
    audio_file: str = ""
    term: str = ""
    use_text_override: bool = False
    quality_tier: str = ""
    synthesis_strategy: str = "azure-native"
    audio_review_status: str = "unreviewed"
    audio_source_hint: AudioSource | None = None


@dataclass(frozen=True)
class TtsResult:
    ok: bool
    reason: str = ""
    attempts: list[str] = field(default_factory=list)
    audio_source: AudioSource | None = None


def _immediate_process_failure(process: Any, timeout: float = 0.15) -> str:
    wait = getattr(process, "wait", None)
    if not callable(wait):
        return ""
    try:
        return_code = wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return ""
    except Exception as exc:
        return f"playback command status check failed: {exc}"
    if not isinstance(return_code, int) or return_code == 0:
        return ""
    return f"playback command exited immediately with status {return_code}"


class TtsEngine:
    name = "base"

    def speak(self, text: str, settings: TtsSettings) -> bool:
        raise NotImplementedError

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        ok = self.speak(text, settings)
        return TtsResult(ok=ok, reason="" if ok else "backend unavailable")


class QtTextToSpeechEngine(TtsEngine):
    name = "qt-text-to-speech"

    def __init__(self) -> None:
        self._engine: Any | None = None

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            from PyQt6.QtTextToSpeech import QTextToSpeech
        except Exception:
            try:
                from PySide6.QtTextToSpeech import QTextToSpeech
            except Exception as exc:
                raise RuntimeError("Qt TextToSpeech is unavailable") from exc
        self._engine = QTextToSpeech()
        return self._engine

    def speak(self, text: str, settings: TtsSettings) -> bool:
        return self.speak_result(text, settings).ok

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        if settings.audio_backend == "local_audio":
            return TtsResult(False, "system TTS disabled")
        try:
            engine = self._ensure_engine()
        except Exception as exc:
            return TtsResult(False, "Qt TextToSpeech is unavailable", [str(exc)])
        if settings.volume is not None and hasattr(engine, "setVolume"):
            engine.setVolume(max(0, min(100, settings.volume)) / 100)
        if settings.rate and hasattr(engine, "setRate"):
            engine.setRate(max(-10, min(10, settings.rate)) / 10)
        if settings.voice and hasattr(engine, "availableVoices"):
            for voice in engine.availableVoices():
                if settings.voice.casefold() in voice.name().casefold():
                    engine.setVoice(voice)
                    break
        try:
            engine.say(text)
        except Exception as exc:
            return TtsResult(False, "Qt TextToSpeech failed to speak", [str(exc)])
        return TtsResult(True, "playing with Qt TextToSpeech", audio_source="live")


class CommandTtsEngine(TtsEngine):
    name = "platform-command"

    def speak(self, text: str, settings: TtsSettings) -> bool:
        return self.speak_result(text, settings).ok

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        if settings.audio_backend == "local_audio":
            return TtsResult(False, "system TTS disabled")
        system = platform.system()
        command: list[str] | None = None
        if system == "Darwin" and shutil.which("say"):
            command = ["say"]
            if settings.voice:
                command.extend(["-v", settings.voice])
            if settings.rate:
                words_per_minute = max(80, min(360, 180 + (settings.rate * 18)))
                command.extend(["-r", str(words_per_minute)])
            command.append(text)
        elif system == "Windows" and shutil.which("powershell"):
            safe_text = text.replace("'", "''")
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Speak('{safe_text}')"
                ),
            ]
        elif shutil.which("spd-say"):
            command = ["spd-say", text]
        elif shutil.which("espeak"):
            command = ["espeak", text]

        if not command:
            return TtsResult(False, "no system TTS command is available")
        try:
            process = subprocess.Popen(command)
        except Exception as exc:
            return TtsResult(False, "system TTS command failed to start", [str(exc)])
        failure = _immediate_process_failure(process)
        if failure:
            return TtsResult(False, "system TTS command failed to start", [failure])
        return TtsResult(True, "playing with system TTS command", audio_source="live")


class LocalAudioFileEngine(TtsEngine):
    name = "local-audio-file"

    def __init__(self, addon_root: Path) -> None:
        self.addon_root = addon_root

    def speak(self, text: str, settings: TtsSettings) -> bool:
        return self.speak_result(text, settings).ok

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        if settings.audio_backend not in {"local_audio", "local_audio_then_tts"}:
            return TtsResult(False, "local audio disabled")
        audio_path = self._resolve_audio_file(settings.audio_file)
        if audio_path is None:
            return TtsResult(False, "local audio unavailable")
        result = self.play_path(audio_path)
        if not result.ok:
            return result
        source: AudioSource = (
            settings.audio_source_hint
            if settings.audio_source_hint in {"custom", "azure"}
            else "azure"
        )
        return TtsResult(True, result.reason, result.attempts, source)

    def play_path(self, audio_path: Path) -> TtsResult:
        anki_result = self._play_with_anki(audio_path)
        if anki_result is not None:
            return anki_result
        command = self._playback_command(audio_path)
        if command is None:
            return TtsResult(False, "no local audio playback command is available")
        try:
            process = subprocess.Popen(command)
        except Exception as exc:
            return TtsResult(False, "local audio playback failed to start", [str(exc)])
        failure = _immediate_process_failure(process)
        if failure:
            return TtsResult(False, "local audio playback failed to start", [failure])
        return TtsResult(True, "playing local audio")

    def _play_with_anki(self, audio_path: Path) -> TtsResult | None:
        try:
            from aqt.sound import av_player
        except Exception:
            return None
        try:
            av_player.play_file(str(audio_path))
        except Exception as exc:
            return TtsResult(False, "Anki audio playback failed", [str(exc)])
        return TtsResult(True, "playing with Anki audio player")

    def _resolve_audio_file(self, audio_file: str) -> Path | None:
        if not audio_file:
            return None
        relative = Path(audio_file)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        candidates = [
            self.addon_root / relative,
            self.addon_root / "user_files" / "audio" / relative.name,
        ]
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if _is_relative_to(resolved, self.addon_root) and audio_file_has_content(resolved):
                return resolved
        return None

    def _playback_command(self, audio_path: Path) -> list[str] | None:
        system = platform.system()
        if system == "Darwin" and shutil.which("afplay"):
            return ["afplay", str(audio_path)]
        if system == "Windows" and shutil.which("powershell"):
            safe_path = str(audio_path).replace("'", "''")
            return [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName presentationCore; "
                    "$p = New-Object system.windows.media.mediaplayer; "
                    f"$p.open('{safe_path}'); $p.play(); "
                    "Start-Sleep -Milliseconds 250; "
                    "while($p.NaturalDuration.HasTimeSpan -and "
                    "$p.Position -lt $p.NaturalDuration.TimeSpan) { "
                    "Start-Sleep -Milliseconds 100 }"
                ),
            ]
        for player in ("paplay", "aplay", "mpg123", "ffplay"):
            if shutil.which(player):
                if player == "ffplay":
                    return [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(audio_path)]
                return [player, str(audio_path)]
        return None


class GeneratedAudioFileEngine(TtsEngine):
    name = "generated-audio-file"

    def __init__(self, addon_root: Path) -> None:
        self.addon_root = addon_root
        self.cache_dir = addon_root / "user_files" / "generated_audio"
        self._player = LocalAudioFileEngine(addon_root)

    def speak(self, text: str, settings: TtsSettings) -> bool:
        return self.speak_result(text, settings).ok

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        if settings.audio_backend not in {"local_audio", "local_audio_then_tts"}:
            return TtsResult(False, "generated audio disabled")
        source_text = text if settings.use_text_override else (settings.term or text)
        speech_text = " ".join(source_text.split())
        if not speech_text:
            return TtsResult(False, "empty speech text")
        audio_path = self._cache_path(settings.term or speech_text)
        if not audio_file_has_content(audio_path) and not self._generate_audio(
            speech_text, audio_path, settings
        ):
            return TtsResult(False, "generated audio unavailable")
        relative_path = audio_path.relative_to(self.addon_root).as_posix()
        result = self._player.speak_result(
            text,
            TtsSettings(
                voice=settings.voice,
                rate=settings.rate,
                volume=settings.volume,
                audio_backend=settings.audio_backend,
                audio_file=relative_path,
                term=settings.term,
                use_text_override=settings.use_text_override,
                quality_tier=settings.quality_tier,
                audio_source_hint="generated",
            ),
        )
        if not result.ok:
            return TtsResult(False, result.reason or "generated audio playback failed", result.attempts)
        return TtsResult(True, "playing generated audio", result.attempts, "generated")

    def _cache_path(self, key: str) -> Path:
        slug = _audio_slug(key) or "pronounceit_term"
        return self.cache_dir / f"{slug}.aiff"

    def _generate_audio(self, speech_text: str, output_path: Path, settings: TtsSettings) -> bool:
        say = shutil.which("say")
        if not say:
            return False
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        command = [say]
        if settings.voice:
            command.extend(["-v", settings.voice])
        command.extend(["-o", str(output_path), speech_text])
        try:
            result = subprocess.run(command, text=True, capture_output=True)
            return result.returncode == 0 and audio_file_has_content(output_path)
        except Exception:
            return False


class AudioPackEngine(TtsEngine):
    name = "offline-pronunciation-pack"

    def __init__(self, addon_root: Path, manager: AudioPackManager | None = None) -> None:
        self.manager = manager or AudioPackManager(addon_root)
        self._player = LocalAudioFileEngine(addon_root)

    def speak(self, text: str, settings: TtsSettings) -> bool:
        return self.speak_result(text, settings).ok

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        if settings.audio_backend not in {"local_audio", "local_audio_then_tts"}:
            return TtsResult(False, "offline pronunciation pack disabled")
        term = " ".join((settings.term or text).split())
        if not term:
            return TtsResult(False, "empty audio pack term")
        audio_path = self.manager.resolve(term)
        if audio_path is None:
            return TtsResult(False, "offline pronunciation pack unavailable")
        result = self._player.play_path(audio_path)
        if not result.ok:
            return TtsResult(False, result.reason, result.attempts)
        details = [
            *result.attempts,
            f"pack-version: {audio_path.parent.name}",
            f"asset: {audio_path.stem}",
            "audio-review: passed",
        ]
        return TtsResult(True, "playing offline pronunciation pack", details, "azure")


class CompositeTtsEngine(TtsEngine):
    name = "composite"

    def __init__(self, engines: list[TtsEngine] | None = None) -> None:
        self.engines = engines or [QtTextToSpeechEngine(), CommandTtsEngine()]

    def speak(self, text: str, settings: TtsSettings) -> bool:
        return self.speak_result(text, settings).ok

    def speak_result(self, text: str, settings: TtsSettings) -> TtsResult:
        if not text.strip():
            return TtsResult(False, "empty speech text")
        attempts: list[str] = []
        last_reason = "no audio backend succeeded"
        for engine in self.engines:
            try:
                result = engine.speak_result(text, settings)
                reason = result.reason or ("ok" if result.ok else "unavailable")
                attempts.append(f"{engine.name}: {reason}")
                attempts.extend(result.attempts)
                if result.ok:
                    return TtsResult(True, reason, attempts, result.audio_source)
                last_reason = reason
            except Exception as exc:
                last_reason = f"{engine.name} failed"
                attempts.append(f"{engine.name}: {exc}")
                continue
        if settings.audio_backend == "local_audio":
            last_reason = "local audio unavailable"
        return TtsResult(False, last_reason, attempts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _audio_slug(value: str) -> str:
    import re

    slug = value.casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")
