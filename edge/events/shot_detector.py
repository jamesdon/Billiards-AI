from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from core.types import BallClass, BallId, Event, EventType, GameState


@dataclass
class ShotDetectorConfig:
    cue_accel_thres: float = 2.5  # m/s^2
    rest_speed_thres: float = 0.03  # m/s
    rest_time_s: float = 0.8


@dataclass
class ShotDetector:
    cfg: ShotDetectorConfig = ShotDetectorConfig()
    _rest_start_ts: Optional[float] = None
    _last_vel: Dict[BallId, Tuple[float, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._last_vel is None:
            self._last_vel = {}

    def update(self, state: GameState, ts: float) -> list[Event]:
        cue_id = self._cue_id(state)
        if cue_id is None or cue_id not in state.balls:
            return []
        cue = state.balls[cue_id]
        vx, vy = cue.vel_xy
        pvx, pvy = self._last_vel.get(cue_id, (vx, vy))
        ax = vx - pvx
        ay = vy - pvy
        accel = (ax * ax + ay * ay) ** 0.5  # assumes ~1s dt; upstream should scale if needed
        self._last_vel[cue_id] = (vx, vy)

        events: list[Event] = []

        if not state.shot.in_shot and accel >= self.cfg.cue_accel_thres:
            events.append(Event(type=EventType.SHOT_START, ts=ts, payload={"cue_ball_id": cue_id}))
            self._rest_start_ts = None

        # shot end when everyone at rest for rest_time_s
        all_speeds = [
            (t.vel_xy[0] ** 2 + t.vel_xy[1] ** 2) ** 0.5 for bid, t in state.balls.items() if bid not in state.pocketed
        ]
        max_speed = max(all_speeds) if all_speeds else 0.0
        if state.shot.in_shot and max_speed <= self.cfg.rest_speed_thres:
            if self._rest_start_ts is None:
                self._rest_start_ts = ts
            elif ts - self._rest_start_ts >= self.cfg.rest_time_s:
                events.append(Event(type=EventType.SHOT_END, ts=ts, payload={}))
                self._rest_start_ts = None
        else:
            self._rest_start_ts = None

        return events

    def _cue_id(self, state: GameState) -> Optional[BallId]:
        for bid, t in state.balls.items():
            if t.best_class() == BallClass.CUE:
                return bid
        return None

