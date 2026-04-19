"""Achievement eligibility helpers (call after ``RuleEngine`` has applied ``SHOT_END``)."""

from __future__ import annotations

from .types import GameState


def is_successful_shot(state: GameState) -> bool:
    """
    A stroke is **successful** for achievement purposes when the rules engine recorded
    no fouls on that shot (``state.shot.fouls_this_shot`` is empty).

    Invoke only after ``rules.on_event(..., SHOT_END)`` so foul lists are complete.
    """
    return len(state.shot.fouls_this_shot) == 0
