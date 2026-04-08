from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.types import BallId, Event, EventType, GameState


@dataclass
class RailHitDetectorConfig:
    rail_band_m: float = 0.05
    min_speed_mps: float = 0.12
    cooldown_s: float = 0.15


def _speed(vxy: Tuple[float, float]) -> float:
    return float((vxy[0] * vxy[0] + vxy[1] * vxy[1]) ** 0.5)


@dataclass
class RailHitDetector:
    cfg: RailHitDetectorConfig = field(default_factory=RailHitDetectorConfig)
    _last_vel: Dict[BallId, Tuple[float, float]] = field(default_factory=dict)
    _last_emit_ts: Dict[BallId, float] = field(default_factory=dict)

    def update(self, state: GameState, ts: float) -> List[Event]:
        L = float(state.config.table_length_m)
        W = float(state.config.table_width_m)
        events: List[Event] = []

        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            if _speed(t.vel_xy) < self.cfg.min_speed_mps:
                self._last_vel[bid] = t.vel_xy
                continue
            px, py = t.pos_xy
            pvx, pvy = self._last_vel.get(bid, t.vel_xy)
            vx, vy = t.vel_xy
            self._last_vel[bid] = (vx, vy)

            last_ts = self._last_emit_ts.get(bid, -1e9)
            if ts - last_ts < self.cfg.cooldown_s:
                continue

            rail: Optional[str] = None
            # x-direction reversal near left/right rail
            if px <= self.cfg.rail_band_m and (pvx < 0.0 <= vx):
                rail = "left"
            elif px >= (L - self.cfg.rail_band_m) and (pvx > 0.0 >= vx):
                rail = "right"
            # y-direction reversal near top/bottom rail
            elif py <= self.cfg.rail_band_m and (pvy < 0.0 <= vy):
                rail = "top"
            elif py >= (W - self.cfg.rail_band_m) and (pvy > 0.0 >= vy):
                rail = "bottom"

            if rail is not None:
                self._last_emit_ts[bid] = ts
                events.append(Event(type=EventType.RAIL_HIT, ts=ts, payload={"ball_id": bid, "rail": rail}))

        return events

