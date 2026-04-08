from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..types import BallClass, BallId, Event, EventType, FoulType, GameState, GameType


@dataclass
class RuleEngine:
    """
    Deterministic rules engine.

    Contract:
    - Accepts physics-ish events (shot start/end, pocket, collision, foul).
    - Mutates GameState in-place (authoritative state is held by edge runtime).
    """

    def on_event(self, state: GameState, event: Event) -> None:
        if event.type == EventType.SHOT_START:
            self._on_shot_start(state, event)
        elif event.type == EventType.SHOT_END:
            self._on_shot_end(state, event)
        elif event.type == EventType.BALL_POCKETED:
            self._on_ball_pocketed(state, event)
        elif event.type == EventType.BALL_COLLISION:
            self._on_ball_collision(state, event)
        elif event.type == EventType.RAIL_HIT:
            self._on_rail_hit(state, event)
        elif event.type == EventType.FOUL:
            self._on_foul(state, event)
        # Allow each ruleset to declare game end deterministically.
        self._check_end_of_game(state, event)

    def legal_first_contact_ball_id(self, state: GameState) -> Optional[BallId]:
        return None

    def _on_shot_start(self, state: GameState, event: Event) -> None:
        state.shot.in_shot = True
        state.shot.shot_start_ts = event.ts
        state.shot.last_cue_contact_ts = None
        state.shot.first_object_ball_hit = None
        state.shot.pocketed_this_shot.clear()
        state.shot.fouls_this_shot.clear()
        state.shot.rail_hits_this_shot = 0

    def _on_shot_end(self, state: GameState, event: Event) -> None:
        if (
            not state.shot.fouls_this_shot
            and
            state.shot.first_object_ball_hit is not None
            and not state.shot.pocketed_this_shot
            and state.shot.rail_hits_this_shot == 0
        ):
            self._on_foul(
                state,
                Event(type=EventType.FOUL, ts=event.ts, payload={"foul_type": FoulType.NO_RAIL_AFTER_CONTACT.value}),
            )
        state.shot.in_shot = False
        self._end_turn_if_needed(state)

    def _on_ball_pocketed(self, state: GameState, event: Event) -> None:
        ball_id = int(event.payload["ball_id"])
        state.pocketed[ball_id] = event.ts
        state.shot.pocketed_this_shot.append(ball_id)

    def _on_ball_collision(self, state: GameState, event: Event) -> None:
        a = int(event.payload["a"])
        b = int(event.payload["b"])
        cue_id = self._find_cue_ball_id(state)
        if cue_id is None or not state.shot.in_shot:
            return
        if state.shot.first_object_ball_hit is not None:
            return
        if a == cue_id and b != cue_id:
            state.shot.first_object_ball_hit = b
        elif b == cue_id and a != cue_id:
            state.shot.first_object_ball_hit = a

    def _on_foul(self, state: GameState, event: Event) -> None:
        foul_type = str(event.payload.get("foul_type") or event.payload.get("reason") or "unknown")
        state.shot.fouls_this_shot.append(foul_type)
        p = state.current_player()
        p.fouls += 1
        # Default penalty behavior by game family.
        if state.config.game_type in (GameType.EIGHT_BALL, GameType.NINE_BALL, GameType.STRAIGHT_POOL, GameType.UK_POOL):
            # American pool baseline: opponent gets ball-in-hand.
            if state.teams:
                state.ball_in_hand_for_team = (state.current_team_idx + 1) % len(state.teams)
            else:
                state.ball_in_hand_for_team = (state.current_player_idx + 1) % len(state.players)
        elif state.config.game_type == GameType.SNOOKER:
            # Snooker baseline foul points: min 4 unless provided.
            pts = int(event.payload.get("foul_points", 4))
            if state.teams:
                opp = (state.current_team_idx + 1) % len(state.teams)
                state.teams[opp].score += pts
            else:
                opp = (state.current_player_idx + 1) % len(state.players)
                state.players[opp].score += pts

    def _end_turn_if_needed(self, state: GameState) -> None:
        # Default: if foul happened or no balls pocketed, pass turn.
        if state.winner_team is not None:
            return
        foul = bool(state.shot.fouls_this_shot)
        scored = bool(state.shot.pocketed_this_shot)
        if foul or not scored:
            state.next_player()

    def _find_cue_ball_id(self, state: GameState) -> Optional[BallId]:
        for bid, t in state.balls.items():
            if t.best_class() == BallClass.CUE:
                return bid
        return None

    def _check_end_of_game(self, state: GameState, event: Event) -> None:
        return

    def _on_rail_hit(self, state: GameState, event: Event) -> None:
        if state.shot.in_shot:
            state.shot.rail_hits_this_shot += 1

