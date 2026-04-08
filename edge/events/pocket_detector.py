from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.geometry import l2
from core.types import BallId, Event, EventType, GameState, PocketLabel

from ..calib.calib_store import Calibration


@dataclass
class PocketDetectorConfig:
    missing_time_s: float = 0.25
    pocket_margin_m: float = 0.03


@dataclass
class PocketDetector:
    cfg: PocketDetectorConfig = PocketDetectorConfig()
    _last_seen_ts: Dict[BallId, float] = field(default_factory=dict)
    _last_pos: Dict[BallId, Tuple[float, float]] = field(default_factory=dict)

    def update(self, state: GameState, ts: float, calib: Optional[Calibration]) -> List[Event]:
        if calib is None or not calib.pockets:
            return []

        events: List[Event] = []

        # update last seen for live balls
        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            self._last_seen_ts[bid] = ts
            self._last_pos[bid] = t.pos_xy

        # find balls that disappeared (not updated elsewhere) by looking for stale tracks:
        # Here we assume pipeline will remove stale balls from state.balls; this detector handles
        # "went missing" when a ball ID stops appearing in state.balls.
        # We therefore need to check memory keys not present in current balls.
        live_ids = set(state.balls.keys())
        for bid in list(self._last_seen_ts.keys()):
            if bid in live_ids or bid in state.pocketed:
                continue
            dt = ts - self._last_seen_ts[bid]
            if dt < self.cfg.missing_time_s:
                continue
            last_xy = self._last_pos.get(bid)
            if last_xy is None:
                continue
            pocket = self._nearest_pocket(calib, last_xy)
            if pocket is None:
                continue
            label, dist = pocket
            if dist <= (self._pocket_radius(calib, label) + self.cfg.pocket_margin_m):
                events.append(
                    Event(
                        type=EventType.BALL_POCKETED,
                        ts=ts,
                        payload={"ball_id": bid, "pocket_label": label.value},
                    )
                )
                # mark as pocketed in state immediately to prevent duplicate emission
                state.pocketed[bid] = ts
                # cleanup memory
                self._last_seen_ts.pop(bid, None)
                self._last_pos.pop(bid, None)

        return events

    def _nearest_pocket(
        self, calib: Calibration, xy_m: Tuple[float, float]
    ) -> Optional[Tuple[PocketLabel, float]]:
        best = None
        for p in calib.pockets:
            d = l2(xy_m, p.center_xy_m)
            if best is None or d < best[1]:
                best = (p.label, d)
        return best

    def _pocket_radius(self, calib: Calibration, label: PocketLabel) -> float:
        for p in calib.pockets:
            if p.label == label:
                return p.radius_m
        return 0.0

