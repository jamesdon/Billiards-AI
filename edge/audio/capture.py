from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AudioCaptureConfig:
    """Device path or host API name; platform-specific (ALSA on Jetson)."""

    device: str = "default"
    sample_rate_hz: int = 48000
    channels: int = 1
    chunk_ms: int = 20


@dataclass
class AudioRingBuffer:
    """
    Placeholder ring buffer for PCM chunks.

    Wire to `sounddevice`, `pyaudio`, or GStreamer `alsasrc` on-device; correlate
    timestamps with `SHOT_START` / cue-ball contact for micro-foul classifiers.
    """

    cfg: AudioCaptureConfig = field(default_factory=AudioCaptureConfig)
    _chunks: List[bytes] = field(default_factory=list)
    max_chunks: int = 200

    def push(self, pcm: bytes) -> None:
        self._chunks.append(pcm)
        if len(self._chunks) > self.max_chunks:
            self._chunks.pop(0)

    def latest(self) -> Optional[bytes]:
        return self._chunks[-1] if self._chunks else None
