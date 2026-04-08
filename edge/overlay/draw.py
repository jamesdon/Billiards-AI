from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from core.types import GameState


@dataclass
class OverlayConfig:
    draw_trails: bool = True


def _put_text(img: np.ndarray, text: str, xy: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def draw_overlay(frame_bgr: np.ndarray, state: GameState, player_name: Optional[str] = None) -> np.ndarray:
    out = frame_bgr.copy()
    _put_text(out, f"Turn: {player_name or state.current_player().name}", (10, 20), (255, 255, 255))
    _put_text(out, f"Inning: {state.inning}", (10, 40), (255, 255, 255))

    # Ball table-coord overlay only; pixel coords would require inverse homography.
    # For now we show summary counts.
    remaining = len([bid for bid in state.balls if bid not in state.pocketed])
    _put_text(out, f"Balls tracked: {remaining}", (10, 60), (255, 255, 255))

    if state._ui_banner:
        _put_text(out, state._ui_banner, (10, 175), (255, 230, 180))

    if state.shot_history:
        last = state.shot_history[-1]
        tag_values = [t.value for t in last.tags]
        tags_text = ",".join(tag_values) if tag_values else "none"
        _put_text(out, f"Last shot tags: {tags_text}", (10, 80), (200, 255, 200))
        if "follow" in tag_values:
            _put_text(out, f"Follow: {last.follow_distance_m:.2f} m", (10, 100), (200, 255, 200))
        if "draw" in tag_values:
            _put_text(out, f"Draw: {last.draw_distance_m:.2f} m", (10, 120), (200, 255, 200))
        if last.cut_angle_deg is not None:
            _put_text(out, f"Cut: {last.cut_angle_deg:.0f} deg", (10, 140), (200, 255, 200))
    return out

