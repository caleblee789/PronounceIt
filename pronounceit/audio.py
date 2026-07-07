from __future__ import annotations

from pathlib import Path


def aiff_has_audio(path: Path) -> bool:
    try:
        return aiff_bytes_have_audio(path.read_bytes())
    except OSError:
        return False


def aiff_bytes_have_audio(data: bytes) -> bool:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        return False

    frame_count = 0
    sound_bytes = 0
    offset = 12
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "big")
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(data):
            return False
        if chunk_id == b"COMM" and chunk_size >= 6:
            frame_count = int.from_bytes(data[chunk_start + 2 : chunk_start + 6], "big")
        elif chunk_id == b"SSND" and chunk_size > 8:
            sound_bytes = chunk_size - 8
        offset = chunk_end + (chunk_size & 1)

    return frame_count > 0 and sound_bytes > 0


def audio_file_has_content(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
    except OSError:
        return False
    if path.suffix.casefold() in {".aif", ".aiff", ".aifc"}:
        return aiff_has_audio(path)
    if path.suffix.casefold() == ".mp3":
        try:
            return mp3_bytes_have_audio(path.read_bytes())
        except OSError:
            return False
    return True


def mp3_bytes_have_audio(data: bytes) -> bool:
    return mp3_duration_seconds(data) > 0


def mp3_duration_seconds(data: bytes) -> float:
    if len(data) < 4:
        return 0.0
    offset = 0
    if data.startswith(b"ID3") and len(data) >= 10:
        size_bytes = data[6:10]
        if any(byte & 0x80 for byte in size_bytes):
            return 0.0
        tag_size = 0
        for byte in size_bytes:
            tag_size = (tag_size << 7) | byte
        offset = 10 + tag_size
    bitrate_mpeg1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    bitrate_mpeg2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    sample_rates = [44100, 48000, 32000, 0]
    duration = 0.0
    index = offset
    frames = 0
    while index + 4 <= len(data):
        header = int.from_bytes(data[index : index + 4], "big")
        if header >> 21 != 0x7FF:
            index += 1
            continue
        version = (header >> 19) & 0x03
        layer = (header >> 17) & 0x03
        bitrate_index = (header >> 12) & 0x0F
        sample_index = (header >> 10) & 0x03
        padding = (header >> 9) & 0x01
        if version == 0x01 or layer != 0x01:
            index += 1
            continue
        bitrate = (bitrate_mpeg1 if version == 0x03 else bitrate_mpeg2)[bitrate_index]
        sample_rate = sample_rates[sample_index]
        if version == 0x02:
            sample_rate //= 2
        elif version == 0x00:
            sample_rate //= 4
        if not bitrate or not sample_rate:
            index += 1
            continue
        samples = 1152 if version == 0x03 else 576
        frame_size = (
            (144000 * bitrate) // sample_rate + padding
            if version == 0x03
            else (72000 * bitrate) // sample_rate + padding
        )
        if frame_size <= 4 or index + frame_size > len(data):
            index += 1
            continue
        duration += samples / sample_rate
        frames += 1
        index += frame_size
    return duration if frames else 0.0
