from __future__ import annotations

from enum import Enum


class VisionGamePhase(str, Enum):
    """
    High-level table lifecycle inferred from vision + rules (not a replacement for GameState).

    See `docs/FEATURE_GAME_PHASE_VISION.md`.
    """

    UNKNOWN = "unknown"
    NO_RACK = "no_rack"
    RACK_PRESENT = "rack_present"
    OPEN_BREAK_PENDING = "open_break_pending"
    IN_PROGRESS = "in_progress"
    GAME_OVER_VISUAL = "game_over_visual"


def estimate_vision_game_phase(
    *,
    rack_track_count: int,
    ball_track_count: int,
    in_shot: bool,
) -> VisionGamePhase:
    """
    Conservative baseline: uses rack detector presence + ball count + shot flag.

    Refine with break-box geometry, head-string compliance, and league-specific rules.
    """
    if rack_track_count > 0 and ball_track_count >= 10:
        return VisionGamePhase.RACK_PRESENT
    if rack_track_count > 0 and ball_track_count < 10:
        return VisionGamePhase.OPEN_BREAK_PENDING
    if rack_track_count == 0 and ball_track_count == 0:
        return VisionGamePhase.NO_RACK
    if in_shot:
        return VisionGamePhase.IN_PROGRESS
    return VisionGamePhase.IN_PROGRESS
