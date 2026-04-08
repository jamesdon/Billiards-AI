from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..types import BallClass, BallId, Event, EventType, GameState
from .base import RuleEngine


@dataclass
class UKPoolRules(RuleEngine):
    """
    UK-style red/yellow pool baseline.

    - Two groups: UK_RED and UK_YELLOW.
    - Black is endgame; player must clear their colors then pot black legally.
    - Fouls give turn to opponent (ball-in-hand not modeled here).
    """

    def legal_first_contact_ball_id(self, state: GameState) -> Optional[BallId]:
        g = state.current_player().group
        if g is None:
            return None
        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            if t.best_class() == g:
                return bid
        # If cleared, black is legal.
        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            if t.best_class() == BallClass.UK_BLACK:
                return bid
        return None

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

        if bc in (BallClass.UK_RED, BallClass.UK_YELLOW):
            self._assign_groups_if_open(state, bc)
            state.current_player().balls_pocketed.append(bc)

        if bc == BallClass.UK_BLACK:
            if self._player_cleared_group(state) and not state.shot.fouls_this_shot:
                state.winner_team = state.current_team_idx if state.teams else state.current_player_idx
                state.game_over_reason = "black_potted_legally"
            else:
                if state.teams:
                    state.winner_team = (state.current_team_idx + 1) % len(state.teams)
                else:
                    state.winner_team = (state.current_player_idx + 1) % len(state.players)
                state.game_over_reason = "black_potted_illegally"

    def _on_shot_end(self, state: GameState, event: Event) -> None:
        if state.shot.first_object_ball_hit is None:
            self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"reason": "no_contact"}))
        else:
            g = state.current_player().group
            if g is not None:
                first = state.balls.get(state.shot.first_object_ball_hit)
                first_class = first.best_class() if first else BallClass.UNKNOWN
                if not self._player_cleared_group(state):
                    if first_class != g:
                        self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"reason": "wrong_first_contact"}))
                else:
                    if first_class != BallClass.UK_BLACK:
                        self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"reason": "wrong_first_contact"}))

        super()._on_shot_end(state, event)

    def _assign_groups_if_open(self, state: GameState, pocketed_group: BallClass) -> None:
        p = state.current_player()
        if p.group is not None:
            return
        opp = state.players[(state.current_player_idx + 1) % len(state.players)]
        p.group = pocketed_group
        opp.group = BallClass.UK_YELLOW if pocketed_group == BallClass.UK_RED else BallClass.UK_RED

    def _player_cleared_group(self, state: GameState) -> bool:
        g = state.current_player().group
        if g is None:
            return False
        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            if t.best_class() == g:
                return False
        return True

