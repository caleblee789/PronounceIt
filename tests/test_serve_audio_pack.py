import threading
import unittest
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.serve_audio_pack import RangeRequestHandler


class RangeServerTests(unittest.TestCase):
    def test_full_and_partial_downloads(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.bin").write_bytes(b"0123456789")
            try:
                server = ThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    partial(RangeRequestHandler, directory=str(root)),
                )
            except PermissionError:
                self.skipTest("local socket binding is unavailable in this sandbox")
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/sample.bin"
                with urllib.request.urlopen(url) as response:
                    self.assertEqual(response.read(), b"0123456789")
                    self.assertEqual(response.headers["Accept-Ranges"], "bytes")
                request = urllib.request.Request(url, headers={"Range": "bytes=3-6"})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), b"3456")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
