from __future__ import annotations

from dataclasses import dataclass

from ..types import BallClass, Event, EventType, GameState
from .base import RuleEngine


SNOOKER_POINTS = {
    BallClass.SNOOKER_RED: 1,
    BallClass.SNOOKER_YELLOW: 2,
    BallClass.SNOOKER_GREEN: 3,
    BallClass.SNOOKER_BROWN: 4,
    BallClass.SNOOKER_BLUE: 5,
    BallClass.SNOOKER_PINK: 6,
    BallClass.SNOOKER_BLACK: 7,
}


@dataclass
class SnookerRules(RuleEngine):
    """
    Snooker baseline:
    - Sequence is reds and colors alternating while reds remain.
    - After reds are gone, colors must be potted in order (yellow..black).
    - This module tracks the "expected target type" per shot in a simplified way.
    """

    expected: BallClass = BallClass.SNOOKER_RED
    # After potting a red, the next stroke may legally contact any color (not a red) first.
    # Kept separate from BallClass.UNKNOWN so "unknown ball identity" is never confused with rules state.
    expect_any_colored_ball: bool = False

    def _on_shot_start(self, state: GameState, event: Event) -> None:
        super()._on_shot_start(state, event)
        # expected remains from previous state

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
        pts = SNOOKER_POINTS.get(bc)
        if pts is not None:
            state.current_player().score += pts
            team = state.current_team()
            if team is not None:
                team.score += pts

    def _on_shot_end(self, state: GameState, event: Event) -> None:
        # Wrong first contact = foul if not expected ball type.
        hit = state.shot.first_object_ball_hit
        if hit is None:
            self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"reason": "no_contact"}))
        else:
            bc = state.balls.get(hit).best_class() if hit in state.balls else BallClass.UNKNOWN
            if not self._is_legal_target(state, bc):
                self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"reason": "wrong_first_contact"}))

        # Update expected target based on remaining reds and what was potted.
        self._update_expected(state)
        super()._on_shot_end(state, event)

    def _check_end_of_game(self, state: GameState, event: Event) -> None:
        if state.winner_team is not None:
            return
        # End-of-frame/game baseline: when all object balls are pocketed, highest score wins.
        remaining = [
            bid
            for bid, t in state.balls.items()
            if (bid not in state.pocketed) and (t.best_class() != BallClass.CUE)
        ]
        if remaining:
            return
        # Determine winner by score.
        if state.teams:
            best = max(range(len(state.teams)), key=lambda i: state.teams[i].score)
            # tie-break not handled (black re-spot etc.); mark as tie if equal.
            scores = [t.score for t in state.teams]
            if scores.count(scores[best]) > 1:
                state.game_over_reason = "tie_requires_respotted_black"
                return
            state.winner_team = best
            state.game_over_reason = "all_balls_pocketed"
        else:
            best = max(range(len(state.players)), key=lambda i: state.players[i].score)
            scores = [p.score for p in state.players]
            if scores.count(scores[best]) > 1:
                state.game_over_reason = "tie_requires_respotted_black"
                return
            state.winner_team = best
            state.game_over_reason = "all_balls_pocketed"

    def _reds_remaining(self, state: GameState) -> bool:
        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            if t.best_class() == BallClass.SNOOKER_RED:
                return True
        return False

    def _update_expected(self, state: GameState) -> None:
        if self._reds_remaining(state):
            # If any red potted this shot => next expected is any color; else expect red.
            potted_classes = [
                state.balls[bid].best_class()
                for bid in state.shot.pocketed_this_shot
                if bid in state.balls
            ]
            if BallClass.SNOOKER_RED in potted_classes:
                self.expect_any_colored_ball = True
            else:
                self.expect_any_colored_ball = False
                self.expected = BallClass.SNOOKER_RED
        else:
            self.expect_any_colored_ball = False
            # Colors in order once reds gone.
            order = [
                BallClass.SNOOKER_YELLOW,
                BallClass.SNOOKER_GREEN,
                BallClass.SNOOKER_BROWN,
                BallClass.SNOOKER_BLUE,
                BallClass.SNOOKER_PINK,
                BallClass.SNOOKER_BLACK,
            ]
            for c in order:
                # find if any remaining
                remaining = any(
                    (bid not in state.pocketed) and (t.best_class() == c) for bid, t in state.balls.items()
                )
                if remaining:
                    self.expected = c
                    return
            # all done -> winner by score (not handled here)

    def _is_legal_target(self, state: GameState, bc: BallClass) -> bool:
        if self.expect_any_colored_ball:
            return bc != BallClass.SNOOKER_RED and bc in SNOOKER_POINTS
        return bc == self.expected

