from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.types import BallClass, Event, EventType, FoulType, GameState


@dataclass
class FoulDetector:
    """
    Emits "immediate" fouls that are best detected outside the rules module.

    Rule modules still enforce wrong-first and no-contact at shot end; this detector
    focuses on:
    - scratch (cue ball pocketed)
    """

    def update(self, state: GameState, ts: float) -> List[Event]:
        cue_id = self._cue_id(state)
        if cue_id is None:
            return []
        if cue_id in state.pocketed and state.shot.in_shot:
            return [Event(type=EventType.FOUL, ts=ts, payload={"foul_type": FoulType.CUE_BALL_SCRATCH.value})]
        return []

    def _cue_id(self, state: GameState) -> Optional[int]:
        for bid, t in state.balls.items():
            if t.best_class() == BallClass.CUE:
                return bid
        return None

