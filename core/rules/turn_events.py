from __future__ import annotations

from typing import Any, Dict, List

from ..types import Event, EventType, GameState


def player_snapshot_payload(state: GameState, player_idx: int, team_idx: int) -> Dict[str, Any]:
    """Stable payload for who holds the table at a turn boundary."""
    p = state.players[player_idx]
    return {
        "player_idx": player_idx,
        "team_idx": team_idx,
        "name": p.name,
        "profile_id": p.profile_id,
    }


def initial_player_turn_begin_event(state: GameState, ts: float) -> Event:
    """Emit once at session start so clients know the opening shooter before any shot."""
    return Event(
        type=EventType.PLAYER_TURN_BEGIN,
        ts=ts,
        payload=player_snapshot_payload(state, state.current_player_idx, state.current_team_idx),
    )


def player_turn_events_after_shot_end(
    state: GameState,
    previous_player_idx: int,
    previous_team_idx: int,
    ts: float,
) -> List[Event]:
    """
    After RuleEngine handles SHOT_END, emit turn-over / turn-begin if rotation changed.

    Uses indices captured *before* ``rules.on_event(..., SHOT_END)`` so the outgoing
    player matches the shooter whose shot just ended.
    """
    if state.winner_team is not None:
        return []
    if (
        state.current_player_idx == previous_player_idx
        and state.current_team_idx == previous_team_idx
    ):
        return []
    return [
        Event(
            type=EventType.PLAYER_TURN_OVER,
            ts=ts,
            payload=player_snapshot_payload(state, previous_player_idx, previous_team_idx),
        ),
        Event(
            type=EventType.PLAYER_TURN_BEGIN,
            ts=ts,
            payload=player_snapshot_payload(state, state.current_player_idx, state.current_team_idx),
        ),
    ]
