import threading
import time
import unittest

from pronounceit.audio_pack import AudioPackCancelled, AudioPackStatus
from pronounceit.audio_pack_download import AudioPackDownloadController


class FakeAudioPackManager:
    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Event()
        self.status_ready = threading.Event()
        self.status_ready.set()
        self.paused = False
        self.cancelled = False
        self.removed = False
        self.installed = False
        self.downloaded_bytes = 0
        self.progress = None

    def status(self, verify_hashes: bool = False) -> AudioPackStatus:
        self.status_ready.wait(timeout=2)
        return AudioPackStatus(
            installed=self.installed,
            compatible=self.installed,
            version="2" if self.installed else "",
            downloaded_shards=16 if self.installed else 0,
            total_shards=16 if self.installed else 0,
            downloaded_bytes=800 if self.installed else self.downloaded_bytes,
            total_bytes=800 if self.installed or self.downloaded_bytes else 0,
            message="Audio pack 2 is installed and ready." if self.installed else "Audio pack is not installed.",
            active_version="2" if self.installed else "",
            verified=self.installed and verify_hashes,
        )

    def prepare_download(self):
        self.paused = False
        self.cancelled = False

    def download(self, progress, *, prepared=False):
        self.progress = progress
        self.started.set()
        self.downloaded_bytes = 100
        progress(100, 800, "0")
        self.release.wait(timeout=2)
        if self.cancelled:
            raise AudioPackCancelled("audio pack download cancelled")
        self.installed = True
        return self.status(True)

    def verify(self):
        return self.status(True)

    def pause(self):
        self.paused = True
        return True

    def resume(self):
        self.paused = False

    def cancel(self):
        self.cancelled = True
        return True

    def remove(self):
        self.removed = True
        self.installed = False
        self.downloaded_bytes = 0


class AudioPackDownloadControllerTests(unittest.TestCase):
    def wait_for(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("condition did not become true")

    def test_download_outlives_ui_scope_and_rejects_duplicate_start(self) -> None:
        manager = FakeAudioPackManager()
        manager.status_ready.clear()
        notices = []
        controller = AudioPackDownloadController(
            manager,
            dispatch=lambda callback: callback(),
            notifier=lambda message, error: notices.append((message, error)),
        )

        self.assertEqual(controller.refresh().phase, "loading")
        manager.status_ready.set()
        self.wait_for(lambda: controller.snapshot().phase == "idle")
        self.assertTrue(controller.start())
        self.assertTrue(manager.started.wait(timeout=1))
        self.assertFalse(controller.start())
        self.wait_for(lambda: controller.snapshot().phase == "downloading")
        self.assertEqual(controller.snapshot().phase, "downloading")

        manager.release.set()
        self.wait_for(lambda: controller.snapshot().installed)
        self.wait_for(lambda: bool(notices))
        self.assertEqual(
            notices,
            [("Offline pronunciation pack download completed.", False)],
        )

    def test_pause_resume_and_cancel_are_process_lifetime_operations(self) -> None:
        manager = FakeAudioPackManager()
        controller = AudioPackDownloadController(manager)
        self.wait_for(lambda: controller.snapshot().phase == "idle")
        self.assertTrue(controller.start())
        self.assertTrue(manager.started.wait(timeout=1))

        self.assertTrue(controller.pause())
        self.assertTrue(controller.snapshot().paused)
        self.assertTrue(manager.paused)
        self.assertTrue(controller.resume())
        self.assertFalse(controller.snapshot().paused)
        self.assertFalse(manager.paused)
        self.assertTrue(controller.cancel())
        manager.progress(100, 800, "0")  # A final transfer update can arrive after cancellation.
        self.assertEqual(controller.snapshot().phase, "cancelling")
        self.assertFalse(controller.cancel())
        manager.release.set()
        self.wait_for(lambda: controller.snapshot().phase == "cancelled")
        self.assertEqual(controller.snapshot().error, "")
        self.assertIn("resume later", controller.snapshot().message)
        self.assertEqual(controller.snapshot().done_bytes, 100)
        self.assertEqual(controller.snapshot().total_bytes, 800)
        self.assertEqual(controller.refresh().phase, "cancelled")
        self.assertIn("resume later", controller.refresh().message)

    def test_verify_and_remove_refresh_shared_state(self) -> None:
        manager = FakeAudioPackManager()
        manager.installed = True
        controller = AudioPackDownloadController(manager)

        self.wait_for(lambda: controller.snapshot().installed)
        self.assertFalse(controller.snapshot().verified)
        self.assertTrue(controller.start_verify())
        self.wait_for(lambda: controller.snapshot().verified)
        self.assertTrue(controller.remove())
        self.wait_for(lambda: controller.snapshot().phase == "idle")
        self.assertTrue(manager.removed)
        self.assertFalse(controller.snapshot().installed)


if __name__ == "__main__":
    unittest.main()
