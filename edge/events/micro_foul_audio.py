from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.types import Event, GameState

from ..audio.capture import AudioRingBuffer


@dataclass
class MicroFoulAudioDetector:
    """
    Correlates microphone energy / future classifier scores with shot windows.

    Stub: returns no events until audio + model integration is added.
    """

    audio: Optional[AudioRingBuffer] = None
    _last_shot_start_ts: Optional[float] = None

    def on_shot_start(self, ts: float) -> None:
        self._last_shot_start_ts = ts

    def update(self, state: GameState, ts: float) -> List[Event]:
        _ = state
        _ = ts
        if self.audio is None:
            return []
        _ = self.audio.latest()
        return []
