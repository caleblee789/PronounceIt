from __future__ import annotations

import argparse
import os
import re
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


RANGE_PATTERN = re.compile(r"bytes=(\d+)-(\d*)$")


class RangeRequestHandler(SimpleHTTPRequestHandler):
    range_start = 0
    range_end: int | None = None
    chunk_delay_seconds = 0.0

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            source = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        size = os.fstat(source.fileno()).st_size
        match = RANGE_PATTERN.fullmatch(self.headers.get("Range", ""))
        start = 0
        end = size - 1
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else end
            if start >= size or end < start:
                source.close()
                self.send_error(416, "Requested Range Not Satisfiable")
                return None
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(os.fstat(source.fileno()).st_mtime))
        self.end_headers()
        source.seek(start)
        self.range_start = start
        self.range_end = end
        return source

    def copyfile(self, source, outputfile) -> None:
        remaining = None if self.range_end is None else self.range_end - self.range_start + 1
        while remaining is None or remaining > 0:
            chunk = source.read(64 * 1024 if remaining is None else min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            if self.chunk_delay_seconds:
                time.sleep(self.chunk_delay_seconds)
            if remaining is not None:
                remaining -= len(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve verified audio-pack artifacts with Range support.")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--chunk-delay-ms",
        type=float,
        default=0,
        help="Optional per-64-KiB delay for interruption/resume testing.",
    )
    args = parser.parse_args()
    class ConfiguredRangeRequestHandler(RangeRequestHandler):
        chunk_delay_seconds = max(0.0, args.chunk_delay_ms / 1000)

    handler = lambda *values, **kwargs: ConfiguredRangeRequestHandler(
        *values,
        directory=str(args.directory.resolve()),
        **kwargs,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {args.directory} at http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
