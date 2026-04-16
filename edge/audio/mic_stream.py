from __future__ import annotations

import threading
from typing import Any, Optional, Union

from .capture import AudioRingBuffer

Device = Union[str, int, None]


class MicStreamController:
    """
    Non-blocking microphone capture into `AudioRingBuffer` via optional `sounddevice`.

    Install: see `requirements-audio.txt` (PortAudio / libportaudio). On Jetson,
    ALSA device strings such as ``hw:1,0`` are accepted when PortAudio exposes them.
    """

    def __init__(self) -> None:
        self._stream: Any = None
        self._stop = threading.Event()

    def start(
        self,
        buffer: AudioRingBuffer,
        *,
        device: Device = None,
        sample_rate_hz: int = 48000,
    ) -> bool:
        try:
            import sounddevice as sd
        except ImportError:
            return False

        self._stop.clear()
        block = max(128, int(sample_rate_hz * 0.02))

        def callback(indata, frames, t_meta, status):  # noqa: ARG001
            if self._stop.is_set():
                return
            buffer.push(indata.tobytes())

        try:
            stream = sd.InputStream(
                device=device,
                channels=1,
                dtype="int16",
                samplerate=sample_rate_hz,
                blocksize=block,
                callback=callback,
            )
            stream.start()
        except Exception:
            return False
        self._stream = stream
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def parse_mic_device_arg(s: Optional[str]) -> Device:
    """``None`` / empty → default capture device; numeric string → device index."""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    return t
