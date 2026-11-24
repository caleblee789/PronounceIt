from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import Callable

from .audio_pack import AudioPackCancelled, AudioPackManager, AudioPackStatus


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
    active_version: str = ""
    target_version: str = ""
    compatible: bool = False
    verified: bool = False

    @property
    def running(self) -> bool:
        return self.phase in {"loading", "preparing", "downloading", "paused", "cancelling", "verifying", "removing"}


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
        self._state = AudioPackDownloadState(phase="loading", message="Checking the audio library…")
        self._start_worker(self._load_status_worker, "Status")

    def snapshot(self) -> AudioPackDownloadState:
        with self._lock:
            return self._state

    def _start_worker(self, operation: Callable[[], None], name: str) -> None:
        threading.Thread(target=operation, name=f"PronounceItAudioPack{name}", daemon=True).start()

    def start(self) -> bool:
        with self._lock:
            if self._state.running:
                return False
            self.manager.prepare_download()
            self._state = replace(
                self._state,
                phase="preparing",
                message="Preparing offline pronunciation pack download…",
                error="",
                verified=False,
            )
            self._start_worker(self._download_worker, "Download")
            return True

    def start_verify(self) -> bool:
        with self._lock:
            if self._state.running:
                return False
            self._state = replace(
                self._state,
                phase="verifying",
                message="Verifying offline pronunciation pack…",
                error="",
                paused=False,
            )
            self._start_worker(self._verify_worker, "Verify")
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
            if self._state.phase not in {"preparing", "downloading", "paused"} or not self.manager.cancel():
                return False
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
            self._state = replace(self._state, phase="removing", message="Removing the audio library…", error="")
            self._start_worker(self._remove_worker, "Remove")
            return True

    def refresh(self) -> AudioPackDownloadState:
        return self.snapshot()

    def _load_status_worker(self) -> None:
        try:
            status = self.manager.status()
        except Exception as exc:
            self._finish_error(str(exc), "Could not check the audio library.", state=self.snapshot())
            return
        with self._lock:
            self._state = self._state_from_status(status)

    def _download_worker(self) -> None:
        try:
            status = self.manager.download(self._progress, prepared=True)
        except AudioPackCancelled:
            self._finish_cancelled()
            return
        except Exception as exc:
            self._finish_error(str(exc), "Download failed.")
            return
        self._finish_success(status, "Offline pronunciation pack download completed.")

    def _verify_worker(self) -> None:
        try:
            status = self.manager.verify()
        except Exception as exc:
            self._finish_error(str(exc), "Verification failed.")
            return
        if not status.installed:
            self._finish_error(status.message, "Verification failed.", state=self._state_from_status(status))
            return
        self._finish_success(status, "Offline pronunciation pack verification passed.")

    def _remove_worker(self) -> None:
        try:
            self.manager.remove()
            status = self.manager.status()
        except Exception as exc:
            self._finish_error(str(exc), "Could not remove the audio library.")
            return
        self._finish_success(status, "Offline pronunciation pack removed.")

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

    def _finish_success(self, status: AudioPackStatus, message: str) -> None:
        with self._lock:
            self._state = self._state_from_status(status)
        self._dispatch(lambda: self._notifier(message, False))

    def _finish_error(self, message: str, status_message: str, *, state: AudioPackDownloadState | None = None) -> None:
        if state is None:
            state = self._state_after_operation()
        with self._lock:
            self._state = replace(state, phase="failed", message=status_message, error=message)
        self._dispatch(lambda: self._notifier(f"Offline pronunciation pack: {message}", True))

    def _finish_cancelled(self) -> None:
        state = self._state_after_operation()
        with self._lock:
            self._state = replace(
                state,
                phase="cancelled",
                paused=False,
                message="Offline pronunciation pack download cancelled. Downloaded files were kept so you can resume later.",
                error="",
            )
        self._dispatch(lambda: self._notifier("Offline pronunciation pack download cancelled.", False))

    def _state_after_operation(self) -> AudioPackDownloadState:
        try:
            return self._state_from_status(self.manager.status())
        except Exception:
            return replace(self.snapshot(), verified=False, paused=False)

    @staticmethod
    def _state_from_status(status: AudioPackStatus) -> AudioPackDownloadState:
        phase = "idle"
        if status.installed:
            phase = "installed"
        elif status.compatible and status.total_shards:
            phase = "incomplete"
        elif status.active_version and status.version and status.active_version != status.version:
            phase = "update-available"
        return AudioPackDownloadState(
            phase=phase,
            done_bytes=status.downloaded_bytes,
            total_bytes=status.total_bytes,
            message=status.message,
            installed=status.installed,
            downloaded_shards=status.downloaded_shards,
            total_shards=status.total_shards,
            active_version=status.active_version,
            target_version=status.version,
            compatible=status.compatible,
            verified=status.verified,
        )
