from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..types import BallClass, BallId, EightBallRuleSet, Event, EventType, FoulType, GameState
from .base import RuleEngine


@dataclass
class EightBallRules(RuleEngine):
    """
    Practical baseline 8-ball implementation.

    Assumptions:
    - Classifier can label SOLID/STRIPE/EIGHT/CUE with reasonable accuracy.
    - We treat "group assignment" as first pocketed non-cue, non-8 ball after break.
    - Full WPA nuances (open table after break, call-shot, etc.) can be layered later.
    """

    def legal_first_contact_ball_id(self, state: GameState) -> Optional[BallId]:
        player_group = state.current_player().group
        if player_group is None:
            return None  # open table
        # Return any ball of player's group; collision detector will validate actual hit.
        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            if t.best_class() == player_group:
                return bid
        return None

    def _on_ball_pocketed(self, state: GameState, event: Event) -> None:
        super()._on_ball_pocketed(state, event)
        ball_id = int(event.payload["ball_id"])
        track = state.balls.get(ball_id)
        if track is None:
            return
        bc = track.best_class()
        is_break_shot = self._is_break_shot(state)

        if bc == BallClass.CUE:
            self._scratch(state, event.ts)
            return

        # group assignment if needed (ignore 8-ball)
        if bc in (BallClass.SOLID, BallClass.STRIPE):
            self._assign_groups_if_open(state, bc)
            state.current_player().balls_pocketed.append(bc)

        if bc == BallClass.EIGHT:
            # Handle 8-on-break differences.
            if is_break_shot:
                rs = state.config.eight_ball_ruleset
                if rs in (EightBallRuleSet.BCA_WPA, EightBallRuleSet.APA):
                    state.winner_team = state.current_team_idx if state.teams else state.current_player_idx
                    state.game_over_reason = "eight_on_break_win"
                    return
                if rs == EightBallRuleSet.BAR:
                    # Common bar variant: re-rack, continue match (no game end).
                    state.game_over_reason = "eight_on_break_rerack"
                    return

            # Win only if player has cleared their group and did not foul this shot.
            if self._player_cleared_group(state) and not state.shot.fouls_this_shot:
                state.winner_team = state.current_team_idx if state.teams else state.current_player_idx
                state.game_over_reason = "eight_ball_pocketed_legally"
            else:
                # Loss: pocket 8 early or on foul
                if state.teams:
                    state.winner_team = (state.current_team_idx + 1) % len(state.teams)
                else:
                    state.winner_team = (state.current_player_idx + 1) % len(state.players)
                state.game_over_reason = "eight_ball_pocketed_illegally"

    def _on_shot_end(self, state: GameState, event: Event) -> None:
        # Wrong-first contact foul (if groups assigned)
        cue_first = state.shot.first_object_ball_hit
        if cue_first is None:
            self._foul(state, FoulType.NO_CONTACT.value)
        else:
            player_group = state.current_player().group
            first_class = state.balls.get(cue_first).best_class() if cue_first in state.balls else None
            if player_group is not None:
                if first_class not in (player_group, BallClass.EIGHT):
                    self._foul(state, FoulType.WRONG_BALL_FIRST.value)
            else:
                # Open table (groups not yet assigned): any object ball may be hit first except the 8.
                if first_class == BallClass.EIGHT:
                    self._foul(state, FoulType.WRONG_BALL_FIRST.value)

        super()._on_shot_end(state, event)

    def _assign_groups_if_open(self, state: GameState, pocketed_group: BallClass) -> None:
        p = state.current_player()
        if p.group is not None:
            return
        opp = state.players[(state.current_player_idx + 1) % len(state.players)]
        p.group = pocketed_group
        opp.group = BallClass.STRIPE if pocketed_group == BallClass.SOLID else BallClass.SOLID

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

    def _scratch(self, state: GameState, ts: float) -> None:
        # Rule-set difference: scratch while pocketing 8 can be immediate loss in many leagues.
        # Here scratch itself remains a foul; 8-ball outcome logic above handles match result.
        self._foul(state, FoulType.CUE_BALL_SCRATCH.value)

    def _foul(self, state: GameState, reason: str) -> None:
        # Reuse base foul bookkeeping via synthetic event.
        self._on_foul(state, Event(type=EventType.FOUL, ts=state.shot.shot_start_ts or 0.0, payload={"reason": reason}))

    def _is_break_shot(self, state: GameState) -> bool:
        # Baseline heuristic: first inning, first shot, before any prior pocketing.
        return state.inning == 1 and len(state.pocketed) <= 1 and state.shot.shot_start_ts is not None

