from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ..types import BallClass, BallId, Event, EventType, FoulType, GameState, NineBallRuleSet
from .base import RuleEngine


@dataclass
class NineBallRules(RuleEngine):
    """
    Baseline 9-ball rules:
    - Must hit lowest-numbered ball first.
    - Win if 9-ball is pocketed on a legal shot (no foul).
    """

    # Keys are ("team", idx) or ("player", idx) so team 0 and player 0 never collide.
    _consecutive_fouls: Dict[Tuple[str, int], int] = field(default_factory=dict)

    def legal_first_contact_ball_id(self, state: GameState) -> Optional[BallId]:
        # Find lowest numbered ball still on table.
        best: Optional[tuple[int, BallId]] = None
        for bid, t in state.balls.items():
            if bid in state.pocketed:
                continue
            if t.number is None:
                continue
            if best is None or t.number < best[0]:
                best = (t.number, bid)
        return best[1] if best else None

    def _on_ball_pocketed(self, state: GameState, event: Event) -> None:
        super()._on_ball_pocketed(state, event)
        ball_id = int(event.payload["ball_id"])
        track = state.balls.get(ball_id)
        if track is None:
            return
        if track.best_class() == BallClass.CUE:
            self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"foul_type": FoulType.CUE_BALL_SCRATCH.value}))
            return
        if track.number == 9:
            # Legal win requires no foul this shot.
            if not state.shot.fouls_this_shot:
                state.winner_team = state.current_team_idx if state.teams else state.current_player_idx
                state.game_over_reason = "nine_ball_pocketed_legally"

    def _on_shot_end(self, state: GameState, event: Event) -> None:
        legal = self.legal_first_contact_ball_id(state)
        if legal is not None:
            if state.shot.first_object_ball_hit is None:
                self._on_foul(state, Event(type=EventType.FOUL, ts=event.ts, payload={"foul_type": FoulType.NO_CONTACT.value}))
            elif state.shot.first_object_ball_hit != legal:
                self._on_foul(
                    state,
                    Event(type=EventType.FOUL, ts=event.ts, payload={"foul_type": FoulType.WRONG_BALL_FIRST.value}),
                )

        # Ruleset-specific three-foul loss.
        # Enabled for WPA/USAPL style; disabled for APA style by default.
        foul_key: Tuple[str, int] = (
            ("team", state.current_team_idx) if state.teams else ("player", state.current_player_idx)
        )
        had_foul = bool(state.shot.fouls_this_shot)
        if had_foul:
            self._consecutive_fouls[foul_key] = self._consecutive_fouls.get(foul_key, 0) + 1
        else:
            self._consecutive_fouls[foul_key] = 0

        if state.config.nine_ball_ruleset in (NineBallRuleSet.WPA, NineBallRuleSet.USAPL):
            if self._consecutive_fouls.get(foul_key, 0) >= 3 and state.winner_team is None:
                if state.teams:
                    state.winner_team = (state.current_team_idx + 1) % len(state.teams)
                else:
                    state.winner_team = (state.current_player_idx + 1) % len(state.players)
                state.game_over_reason = "three_consecutive_fouls"

        super()._on_shot_end(state, event)

