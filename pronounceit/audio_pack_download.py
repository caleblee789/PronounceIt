from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from .audio_pack import AudioPackManager, AudioPackStatus


Dispatch = Callable[[Callable[[], None]], None]
Notifier = Callable[[str, bool], None]


@dataclass(frozen=True)
class AudioPackDownloadState:
    phase: str = "idle"
    done_bytes: int = 0
    total_bytes: int = 0
    shard: str = ""
    message: str = "Offline pronunciation pack is not installed."
    error: str = ""
    paused: bool = False
    installed: bool = False
    downloaded_shards: int = 0
    total_shards: int = 0

    @property
    def running(self) -> bool:
        return self.phase in {"preparing", "downloading", "paused", "cancelling", "verifying"}


class AudioPackDownloadController:
    """Owns one resumable audio-pack operation for the add-on process lifetime."""

    def __init__(
        self,
        manager: AudioPackManager,
        dispatch: Dispatch | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self.manager = manager
        self._dispatch = dispatch or (lambda callback: callback())
        self._notifier = notifier or (lambda _message, _error: None)
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._last_dispatch = 0.0
        self._state = self._state_from_status(manager.status())

    def snapshot(self) -> AudioPackDownloadState:
        with self._lock:
            return replace(self._state)

    def start(self) -> bool:
        with self._lock:
            if self._state.running or (self._worker and self._worker.is_alive()):
                return False
            self.manager.resume()
            self._state = AudioPackDownloadState(
                phase="preparing",
                message="Preparing offline pronunciation pack download…",
            )
            self._worker = threading.Thread(
                target=self._download_worker,
                name="PronounceItAudioPack",
                daemon=True,
            )
            self._worker.start()
            return True

    def start_verify(self) -> bool:
        with self._lock:
            if self._state.running or (self._worker and self._worker.is_alive()):
                return False
            self._state = replace(
                self._state,
                phase="verifying",
                message="Verifying offline pronunciation pack…",
                error="",
                paused=False,
            )
            self._worker = threading.Thread(
                target=self._verify_worker,
                name="PronounceItAudioPackVerify",
                daemon=True,
            )
            self._worker.start()
            return True

    def pause(self) -> bool:
        with self._lock:
            if self._state.phase not in {"preparing", "downloading"}:
                return False
            self.manager.pause()
            self._state = replace(
                self._state,
                phase="paused",
                paused=True,
                message="Offline pronunciation pack download paused.",
            )
            return True

    def resume(self) -> bool:
        with self._lock:
            if self._state.phase != "paused":
                return False
            self.manager.resume()
            self._state = replace(
                self._state,
                phase="downloading",
                paused=False,
                message="Resuming offline pronunciation pack download…",
            )
            return True

    def cancel(self) -> bool:
        with self._lock:
            if not self._state.running or self._state.phase == "cancelling":
                return False
            self.manager.cancel()
            self._state = replace(
                self._state,
                phase="cancelling",
                paused=False,
                message="Cancelling offline pronunciation pack download…",
                error="",
            )
            return True

    def remove(self) -> bool:
        with self._lock:
            if self._state.running:
                return False
        self.manager.remove()
        with self._lock:
            self._state = self._state_from_status(self.manager.status())
        return True

    def refresh(self) -> AudioPackDownloadState:
        with self._lock:
            if self._state.phase in {"idle", "installed"}:
                self._state = self._state_from_status(self.manager.status())
            return replace(self._state)

    def _download_worker(self) -> None:
        try:
            status = self.manager.download(self._progress)
        except Exception as exc:
            if "cancelled" in str(exc).casefold() or "canceled" in str(exc).casefold():
                self._finish_cancelled()
                return
            self._finish_error(str(exc), "Download failed.")
            return
        self._finish_success(status, "Offline pronunciation pack download completed.")

    def _verify_worker(self) -> None:
        try:
            status = self.manager.verify()
            if not status.installed:
                raise RuntimeError(status.message)
        except Exception as exc:
            self._finish_error(str(exc), "Verification failed.")
            return
        self._finish_success(status, "Offline pronunciation pack verification passed.")

    def _progress(self, done: int, total: int, shard: str) -> None:
        with self._lock:
            paused = self._state.paused
            cancelling = self._state.phase == "cancelling"
            self._state = replace(
                self._state,
                phase="cancelling" if cancelling else "paused" if paused else "downloading",
                done_bytes=max(0, int(done)),
                total_bytes=max(0, int(total)),
                shard=str(shard),
                message=self._state.message if cancelling else (
                    "Offline pronunciation pack download paused."
                    if paused
                    else "Downloading offline pronunciation pack…"
                ),
            )
            now = time.monotonic()
            if now - self._last_dispatch >= 0.25:
                self._last_dispatch = now

    def _finish_success(self, status: AudioPackStatus, message: str) -> None:
        with self._lock:
            self._state = self._state_from_status(status)
        self._dispatch(lambda: self._notifier(message, False))

    def _finish_error(self, message: str, status_message: str) -> None:
        status = self.manager.status()
        with self._lock:
            progress = self._state
            self._state = replace(
                self._state_from_status(status),
                phase="failed",
                done_bytes=max(progress.done_bytes, status.downloaded_bytes),
                total_bytes=max(progress.total_bytes, status.total_bytes),
                shard=progress.shard,
                message=status_message,
                error=message,
            )
        self._dispatch(lambda: self._notifier(f"Offline pronunciation pack: {message}", True))

    def _finish_cancelled(self) -> None:
        status = self.manager.status()
        with self._lock:
            progress = self._state
            self._state = replace(
                self._state_from_status(status),
                phase="cancelled",
                done_bytes=max(progress.done_bytes, status.downloaded_bytes),
                total_bytes=max(progress.total_bytes, status.total_bytes),
                shard=progress.shard,
                message="Offline pronunciation pack download cancelled. Downloaded files were kept so you can resume later.",
                error="",
            )
        self._dispatch(lambda: self._notifier("Offline pronunciation pack download cancelled.", False))

    @staticmethod
    def _state_from_status(status: AudioPackStatus) -> AudioPackDownloadState:
        return AudioPackDownloadState(
            phase="installed" if status.installed else "idle",
            done_bytes=status.downloaded_bytes,
            total_bytes=status.total_bytes,
            message=status.message,
            installed=status.installed,
            downloaded_shards=status.downloaded_shards,
            total_shards=status.total_shards,
        )
