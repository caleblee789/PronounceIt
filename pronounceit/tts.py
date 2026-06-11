from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from typing import Any


AudioBackend = Literal["system_tts", "local_audio", "local_audio_then_tts"]


@dataclass(frozen=True)
class TtsSettings:
    voice: str = ""
    rate: int = 0
    volume: int = 100
    audio_backend: AudioBackend = "system_tts"
    audio_file: str = ""
    term: str = ""


class TtsEngine:
    name = "base"

    def speak(self, text: str, settings: TtsSettings) -> bool:
        raise NotImplementedError


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
        if settings.audio_backend == "local_audio":
            return False
        engine = self._ensure_engine()
        if settings.volume is not None and hasattr(engine, "setVolume"):
            engine.setVolume(max(0, min(100, settings.volume)) / 100)
        if settings.rate and hasattr(engine, "setRate"):
            engine.setRate(max(-10, min(10, settings.rate)) / 10)
        if settings.voice and hasattr(engine, "availableVoices"):
            for voice in engine.availableVoices():
                if settings.voice.casefold() in voice.name().casefold():
                    engine.setVoice(voice)
                    break
        engine.say(text)
        return True


class CommandTtsEngine(TtsEngine):
    name = "platform-command"

    def speak(self, text: str, settings: TtsSettings) -> bool:
        if settings.audio_backend == "local_audio":
            return False
        system = platform.system()
        command: list[str] | None = None
        if system == "Darwin" and shutil.which("say"):
            command = ["say"]
            if settings.voice:
                command.extend(["-v", settings.voice])
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
            return False
        subprocess.Popen(command)
        return True


class LocalAudioFileEngine(TtsEngine):
    name = "local-audio-file"

    def __init__(self, addon_root: Path) -> None:
        self.addon_root = addon_root

    def speak(self, text: str, settings: TtsSettings) -> bool:
        if settings.audio_backend not in {"local_audio", "local_audio_then_tts"}:
            return False
        audio_path = self._resolve_audio_file(settings.audio_file)
        if audio_path is None:
            return False
        command = self._playback_command(audio_path)
        if command is None:
            return False
        subprocess.Popen(command)
        return True

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
            if _is_relative_to(resolved, self.addon_root):
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
        if settings.audio_backend not in {"local_audio", "local_audio_then_tts"}:
            return False
        speech_text = " ".join(text.split())
        if not speech_text:
            return False
        audio_path = self._cache_path(settings.term or speech_text)
        if not audio_path.exists() and not self._generate_audio(speech_text, audio_path, settings):
            return False
        relative_path = audio_path.relative_to(self.addon_root).as_posix()
        return self._player.speak(
            text,
            TtsSettings(
                voice=settings.voice,
                rate=settings.rate,
                volume=settings.volume,
                audio_backend=settings.audio_backend,
                audio_file=relative_path,
                term=settings.term,
            ),
        )

    def _cache_path(self, key: str) -> Path:
        slug = _audio_slug(key) or "pronounceit_term"
        return self.cache_dir / f"{slug}.aiff"

    def _generate_audio(self, speech_text: str, output_path: Path, settings: TtsSettings) -> bool:
        say = shutil.which("say")
        if not say:
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [say]
        if settings.voice:
            command.extend(["-v", settings.voice])
        command.extend(["-o", str(output_path), speech_text])
        result = subprocess.run(command, text=True, capture_output=True)
        return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


class CompositeTtsEngine(TtsEngine):
    name = "composite"

    def __init__(self, engines: list[TtsEngine] | None = None) -> None:
        self.engines = engines or [QtTextToSpeechEngine(), CommandTtsEngine()]

    def speak(self, text: str, settings: TtsSettings) -> bool:
        if not text.strip():
            return False
        for engine in self.engines:
            try:
                if engine.speak(text, settings):
                    return True
            except Exception:
                continue
        return False


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
