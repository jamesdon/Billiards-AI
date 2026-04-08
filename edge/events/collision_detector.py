from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from core.geometry import l2
from core.types import BallId, Event, EventType, GameState


@dataclass
class CollisionDetectorConfig:
    contact_dist_m: float = 0.06
    min_rel_speed_mps: float = 0.10
    cooldown_s: float = 0.15


@dataclass
class CollisionDetector:
    cfg: CollisionDetectorConfig = CollisionDetectorConfig()
    _last_emit_ts: Dict[Tuple[BallId, BallId], float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._last_emit_ts is None:
            self._last_emit_ts = {}

    def update(self, state: GameState, ts: float) -> List[Event]:
        ids = [bid for bid in state.balls.keys() if bid not in state.pocketed]
        events: List[Event] = []
        for i in range(len(ids)):
            a = ids[i]
            ta = state.balls[a]
            for j in range(i + 1, len(ids)):
                b = ids[j]
                tb = state.balls[b]
                if l2(ta.pos_xy, tb.pos_xy) > self.cfg.contact_dist_m:
                    continue
                rvx = ta.vel_xy[0] - tb.vel_xy[0]
                rvy = ta.vel_xy[1] - tb.vel_xy[1]
                rel = float((rvx * rvx + rvy * rvy) ** 0.5)
                if rel < self.cfg.min_rel_speed_mps:
                    continue
                key = (a, b)
                last = self._last_emit_ts.get(key, -1e9)
                if ts - last < self.cfg.cooldown_s:
                    continue
                self._last_emit_ts[key] = ts
                events.append(Event(type=EventType.BALL_COLLISION, ts=ts, payload={"a": a, "b": b}))
        return events

