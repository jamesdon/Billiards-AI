from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .achievements import is_successful_shot
from .types import BallId, Event, EventType, GameState


@dataclass
class LiveStats:
    # Derived metrics
    ball_speeds_mps: Dict[BallId, float] = field(default_factory=dict)
    cue_shot_peak_speed_mps: float = 0.0
    last_shot_duration_s: float = 0.0


@dataclass
class StatsAggregator:
    stats: LiveStats = field(default_factory=LiveStats)
    _shot_start_ts: Optional[float] = None

    def on_state_update(self, state: GameState) -> None:
        self.stats.ball_speeds_mps = {
            bid: float((t.vel_xy[0] ** 2 + t.vel_xy[1] ** 2) ** 0.5)
            for bid, t in state.balls.items()
            if bid not in state.pocketed
        }
        # keep a running shot peak based on cue-ball max speed observed
        if state.shot.in_shot:
            self.stats.cue_shot_peak_speed_mps = max(
                self.stats.cue_shot_peak_speed_mps, state.shot.shot_max_cue_speed_mps
            )

    def on_event(self, state: GameState, event: Event) -> None:
        if event.type == EventType.SHOT_START:
            self._shot_start_ts = event.ts
            self.stats.cue_shot_peak_speed_mps = 0.0
            shooter = state.current_player()
            shooter.shots_taken += 1
        elif event.type == EventType.SHOT_END:
            if self._shot_start_ts is not None:
                self.stats.last_shot_duration_s = max(0.0, event.ts - self._shot_start_ts)
            self._shot_start_ts = None
        elif event.type == EventType.FOUL:
            team = state.current_team()
            if team is not None:
                team.fouls += 1
        elif event.type in (
            EventType.PLAYER_TURN_BEGIN,
            EventType.PLAYER_TURN_OVER,
            EventType.PLAYER_SHOT_BEGIN,
            EventType.PLAYER_SHOT_OVER,
        ):
            # Informational; authoritative turn is always GameState.current_* after rules.
            pass
        elif event.type == EventType.ACHIEVEMENT:
            # Defensive: achievements are emitted only after successful shots; ignore stray events.
            if not is_successful_shot(state):
                return
            at = str(event.payload.get("achievement_type", ""))
            pi = event.payload.get("player_idx")
            if at and isinstance(pi, int) and 0 <= pi < len(state.players):
                p = state.players[pi]
                p.achievement_counts[at] = p.achievement_counts.get(at, 0) + 1

