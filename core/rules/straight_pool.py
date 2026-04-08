from __future__ import annotations

from dataclasses import dataclass

from ..types import BallClass, Event, EventType, GameState
from .base import RuleEngine


@dataclass
class StraightPoolRules(RuleEngine):
    """
    Straight pool (14.1 continuous) baseline:
    - Each legally pocketed object ball = 1 point for shooter.
    - Fouls subtract 1 point (baseline; leagues differ).
    - Turn continues while pocketing continues (unless foul).
    - Rerack logic is table/operator dependent; we emit a marker state via scoring only.
    """

    def _on_ball_pocketed(self, state: GameState, event: Event) -> None:
        super()._on_ball_pocketed(state, event)
        ball_id = int(event.payload["ball_id"])
        track = state.balls.get(ball_id)
        if track is None:
            return
        bc = track.best_class()
        if bc == BallClass.CUE:
            self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"reason": "scratch"}))
            return
        if bc != BallClass.UNKNOWN:
            state.current_player().score += 1
            team = state.current_team()
            if team is not None:
                team.score += 1

    def _on_foul(self, state: GameState, event: Event) -> None:
        super()._on_foul(state, event)
        state.current_player().score -= 1
        team = state.current_team()
        if team is not None:
            team.score -= 1

    def _check_end_of_game(self, state: GameState, event: Event) -> None:
        if state.winner_team is not None:
            return
        target = int(state.config.straight_pool_target_points)
        # Winner is first player/team to reach target points.
        if state.teams:
            for ti, t in enumerate(state.teams):
                if t.score >= target:
                    state.winner_team = ti
                    state.game_over_reason = "target_points_reached"
                    return
        else:
            for pi, p in enumerate(state.players):
                if p.score >= target:
                    state.winner_team = pi
                    state.game_over_reason = "target_points_reached"
                    return

