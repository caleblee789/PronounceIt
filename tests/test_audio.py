import unittest

from pronounceit.audio import aiff_bytes_have_audio, mp3_bytes_have_audio, mp3_duration_seconds


def valid_aiff_bytes() -> bytes:
    comm = b"COMM" + (18).to_bytes(4, "big") + b"\x00\x01" + (1).to_bytes(4, "big")
    comm += b"\x00\x10" + b"\x40\x0e\xac\x44\x00\x00\x00\x00\x00\x00"
    sound = b"SSND" + (10).to_bytes(4, "big") + b"\x00" * 8 + b"\x00\x01"
    body = b"AIFF" + comm + sound
    return b"FORM" + len(body).to_bytes(4, "big") + body


class AudioValidationTests(unittest.TestCase):
    def test_accepts_aiff_with_frames_and_sound_data(self) -> None:
        self.assertTrue(aiff_bytes_have_audio(valid_aiff_bytes()))

    def test_rejects_header_only_aiff(self) -> None:
        header_only = valid_aiff_bytes().replace(
            b"\x00\x00\x00\x01\x00\x10", b"\x00\x00\x00\x00\x00\x10", 1
        )
        self.assertFalse(aiff_bytes_have_audio(header_only))

    def test_rejects_truncated_or_non_aiff_data(self) -> None:
        self.assertFalse(aiff_bytes_have_audio(b"FORM"))
        self.assertFalse(aiff_bytes_have_audio(b"not audio"))

    def test_accepts_mp3_frames_and_reports_duration(self) -> None:
        frame = b"\xff\xfb\x90\x64" + (b"\x00" * 413)
        data = frame * 10

        self.assertTrue(mp3_bytes_have_audio(data))
        self.assertGreater(mp3_duration_seconds(data), 0.2)

    def test_rejects_id3_or_random_bytes_without_mp3_frames(self) -> None:
        self.assertFalse(mp3_bytes_have_audio(b"ID3" + b"\x00" * 100))
        self.assertFalse(mp3_bytes_have_audio(b"not audio"))


if __name__ == "__main__":
    unittest.main()
