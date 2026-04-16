from __future__ import annotations

from edge.audio.capture import AudioRingBuffer


def test_audio_ringbuffer_push_and_latest():
    b = AudioRingBuffer(max_chunks=3)
    b.push(b"\x01\x00")
    b.push(b"\x02\x00")
    assert b.latest() == b"\x02\x00"
    b.push(b"\x03\x00")
    b.push(b"\x04\x00")
    assert b.latest() == b"\x04\x00"


def test_parse_mic_device_arg():
    from edge.audio.mic_stream import parse_mic_device_arg

    assert parse_mic_device_arg(None) is None
    assert parse_mic_device_arg("") is None
    assert parse_mic_device_arg("  ") is None
    assert parse_mic_device_arg("2") == 2
    assert parse_mic_device_arg("default") == "default"
