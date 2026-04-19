from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.geometry import l2
from core.types import AchievementType, BallClass, BallId, Event, EventType, GameState


def _speed(vx: float, vy: float) -> float:
    return float((vx * vx + vy * vy) ** 0.5)


@dataclass
class ThreadTheNeedleConfig:
    """Heuristic: minimum surface gap (m) observed during the stroke vs any obstacle."""

    ball_radius_m: float = 0.028575  # ~2.25" diameter / 2
    max_clearance_m: float = 0.008  # tighter than this counts as "threading"
    min_move_speed_mps: float = 0.08  # ignore idle crowding


@dataclass
class ThreadTheNeedleDetector:
    """
    Tracks near passes (ball–ball and ball–rail) during a shot.

    After rules finish on ``SHOT_END``, if the shot had a successful object-ball pocket
    (no cue scratch) and clearance dropped below ``max_clearance_m``, emit ``ACHIEVEMENT``.
    """

    cfg: ThreadTheNeedleConfig = field(default_factory=ThreadTheNeedleConfig)
    _min_clearance_m: float = 1e9
    _active: bool = False

    def on_shot_start(self) -> None:
        self._min_clearance_m = 1e9
        self._active = True

    def update(self, state: GameState, ts: float) -> None:
        _ = ts
        if not self._active or not state.shot.in_shot:
            return
        L = float(state.config.table_length_m)
        W = float(state.config.table_width_m)
        R = self.cfg.ball_radius_m
        ids = [bid for bid in state.balls if bid not in state.pocketed]
        # Ball–ball clearance (center distance minus two radii).
        for i, a in enumerate(ids):
            ta = state.balls[a]
            if _speed(*ta.vel_xy) < self.cfg.min_move_speed_mps:
                continue
            for b in ids[i + 1 :]:
                tb = state.balls[b]
                if _speed(*tb.vel_xy) < self.cfg.min_move_speed_mps and _speed(*ta.vel_xy) < self.cfg.min_move_speed_mps:
                    continue
                d = l2(ta.pos_xy, tb.pos_xy) - 2.0 * R
                if d < self._min_clearance_m:
                    self._min_clearance_m = d
        # Ball–rail gap (center to cushion line minus radius).
        for bid in ids:
            t = state.balls[bid]
            if _speed(*t.vel_xy) < self.cfg.min_move_speed_mps:
                continue
            px, py = t.pos_xy
            gaps = (px - R, L - px - R, py - R, W - py - R)
            g = min(gaps)
            if g < self._min_clearance_m:
                self._min_clearance_m = g

    def try_emit_achievement(self, state: GameState, ts: float) -> Optional[Event]:
        """
        Call after ``RuleEngine`` has processed ``SHOT_END`` so ``fouls_this_shot`` is complete.
        """
        self._active = False
        if state.winner_team is not None:
            return None
        if self._min_clearance_m >= self.cfg.max_clearance_m:
            state.shot.thread_the_needle_eligible = False
            return None
        if not self._successful_object_pocket(state):
            state.shot.thread_the_needle_eligible = False
            return None
        if state.shot.fouls_this_shot:
            state.shot.thread_the_needle_eligible = False
            return None

        state.shot.thread_the_needle_eligible = True
        shooter = state.current_player_idx
        team = state.current_team_idx if state.teams else state.current_player_idx
        p = state.players[shooter]
        key = AchievementType.THREAD_THE_NEEDLE.value
        return Event(
            type=EventType.ACHIEVEMENT,
            ts=ts,
            payload={
                "achievement_type": key,
                "player_idx": shooter,
                "team_idx": team,
                "name": p.name,
                "profile_id": p.profile_id,
                "min_clearance_m": float(self._min_clearance_m),
                "ball_radius_m": self.cfg.ball_radius_m,
            },
        )

    def _successful_object_pocket(self, state: GameState) -> bool:
        if not state.shot.pocketed_this_shot:
            return False
        cue_id = self._cue_ball_id(state)
        for bid in state.shot.pocketed_this_shot:
            if cue_id is not None and bid == cue_id:
                continue
            tr = state.balls.get(bid)
            if tr is not None and tr.best_class() == BallClass.CUE:
                continue
            return True
        return False

    def _cue_ball_id(self, state: GameState) -> Optional[BallId]:
        for bid, t in state.balls.items():
            if t.best_class() == BallClass.CUE:
                return bid
        return None
