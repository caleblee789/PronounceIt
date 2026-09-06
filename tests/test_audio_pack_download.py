import threading
import time
import unittest

from pronounceit.audio_pack import AudioPackStatus
from pronounceit.audio_pack_download import AudioPackDownloadController


class FakeAudioPackManager:
    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Event()
        self.paused = False
        self.cancelled = False
        self.removed = False
        self.installed = False

    def status(self, verify_hashes: bool = False) -> AudioPackStatus:
        return AudioPackStatus(
            installed=self.installed,
            compatible=self.installed,
            version="2" if self.installed else "",
            downloaded_shards=16 if self.installed else 0,
            total_shards=16 if self.installed else 0,
            downloaded_bytes=800 if self.installed else 0,
            total_bytes=800 if self.installed else 0,
            message="Audio pack 2 is installed and ready." if self.installed else "Audio pack is not installed.",
        )

    def download(self, progress):
        self.started.set()
        progress(100, 800, "0")
        self.release.wait(timeout=2)
        if self.cancelled:
            raise RuntimeError("audio pack download cancelled")
        self.installed = True
        return self.status(True)

    def verify(self):
        return self.status(True)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def cancel(self):
        self.cancelled = True
        self.release.set()

    def remove(self):
        self.removed = True
        self.installed = False


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
        notices = []
        controller = AudioPackDownloadController(
            manager,
            dispatch=lambda callback: callback(),
            notifier=lambda message, error: notices.append((message, error)),
        )

        self.assertTrue(controller.start())
        self.assertTrue(manager.started.wait(timeout=1))
        self.assertFalse(controller.start())
        self.wait_for(lambda: controller.snapshot().phase == "downloading")
        self.assertEqual(controller.snapshot().phase, "downloading")

        manager.release.set()
        self.wait_for(lambda: controller.snapshot().installed)
        self.assertEqual(
            notices,
            [("Offline pronunciation pack download completed.", False)],
        )

    def test_pause_resume_and_cancel_are_process_lifetime_operations(self) -> None:
        manager = FakeAudioPackManager()
        controller = AudioPackDownloadController(manager)
        controller.start()
        self.assertTrue(manager.started.wait(timeout=1))

        self.assertTrue(controller.pause())
        self.assertTrue(controller.snapshot().paused)
        self.assertTrue(manager.paused)
        self.assertTrue(controller.resume())
        self.assertFalse(controller.snapshot().paused)
        self.assertFalse(manager.paused)
        self.assertTrue(controller.cancel())
        self.assertEqual(controller.snapshot().phase, "cancelling")
        self.assertFalse(controller.cancel())
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

        self.assertTrue(controller.start_verify())
        self.wait_for(lambda: controller.snapshot().phase == "installed")
        self.assertTrue(controller.remove())
        self.assertTrue(manager.removed)
        self.assertFalse(controller.snapshot().installed)


if __name__ == "__main__":
    unittest.main()
