from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from core.types import GameState

from ..calib.calib_store import Calibration


@dataclass
class OverlayConfig:
    draw_trails: bool = True


def _put_text(img: np.ndarray, text: str, xy: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def _draw_polyline_table_m(
    out: np.ndarray,
    calib: Calibration,
    poly_m: List[Tuple[float, float]],
    *,
    color: Tuple[int, int, int],
    thickness: int = 2,
) -> None:
    if len(poly_m) < 2:
        return
    pts = np.array([[int(calib.H.to_pixel(xy)[0]), int(calib.H.to_pixel(xy)[1])] for xy in poly_m], dtype=np.int32)
    cv2.polylines(out, [pts], isClosed=False, color=color, thickness=thickness, lineType=cv2.LINE_AA)


def _draw_table_polygon(
    out: np.ndarray,
    calib: Calibration,
    poly_m: list[tuple[float, float]],
    *,
    color: Tuple[int, int, int],
    thickness: int = 2,
    close: bool = True,
) -> None:
    if len(poly_m) < 2:
        return
    pts = []
    for xy in poly_m:
        px, py = calib.H.to_pixel(xy)
        pts.append([int(px), int(py)])
    arr = np.array([pts], dtype=np.int32)
    cv2.polylines(out, arr, isClosed=close, color=color, thickness=thickness)


def draw_overlay(
    frame_bgr: np.ndarray,
    state: GameState,
    player_name: Optional[str] = None,
    calib: Optional[Calibration] = None,
) -> np.ndarray:
    out = frame_bgr.copy()
    _put_text(out, f"Turn: {player_name or state.current_player().name}", (10, 20), (255, 255, 255))
    _put_text(out, f"Inning: {state.inning}", (10, 40), (255, 255, 255))

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

    layers = state.projector_layers
    if calib is not None:
        if layers.show_break_box and calib.break_area_polygon_xy_m:
            _draw_table_polygon(out, calib, calib.break_area_polygon_xy_m, color=(0, 255, 255), thickness=2)
        if layers.show_break_string and len(calib.kitchen_polygon_xy_m) >= 2:
            p0 = calib.H.to_pixel(calib.kitchen_polygon_xy_m[0])
            p1 = calib.H.to_pixel(calib.kitchen_polygon_xy_m[1])
            cv2.line(
                out,
                (int(p0[0]), int(p0[1])),
                (int(p1[0]), int(p1[1])),
                (0, 200, 255),
                2,
                cv2.LINE_AA,
            )

    if layers.show_score:
        y = 200
        for i, p in enumerate(state.players):
            _put_text(out, f"{p.name}: {p.score}", (10, y + i * 18), (255, 255, 200))

    if layers.show_my_stats:
        p = state.current_player()
        _put_text(out, f"Shots: {p.shots_taken} Fouls: {p.fouls}", (10, 280), (200, 220, 255))

    if layers.show_best_next_shot:
        hint_best = getattr(state, "_hint_best_table_m", []) or []
        _put_text(
            out,
            "Best next: stub aim" if hint_best else "Best next: (no cue)",
            (10, 300),
            (180, 255, 180),
        )
        if calib is not None and hint_best:
            _draw_polyline_table_m(out, calib, hint_best, color=(80, 220, 80), thickness=2)
    if layers.show_alt_next_shot:
        hint_alt = getattr(state, "_hint_alt_table_m", []) or []
        _put_text(
            out,
            f"Alt #{layers.alt_shot_variant_index}: stub" if hint_alt else f"Alt #{layers.alt_shot_variant_index}: (no cue)",
            (10, 320),
            (180, 200, 255),
        )
        if calib is not None and hint_alt:
            _draw_polyline_table_m(out, calib, hint_alt, color=(200, 100, 255), thickness=2)

    if layers.highlighted_ball_labels:
        lab = ",".join(layers.highlighted_ball_labels)
        _put_text(out, f"Highlight: {lab}", (10, 340), (255, 180, 100))

    if state.trajectory_assist_enabled:
        _put_text(out, "Trajectory assist: ON", (10, 360), (100, 255, 255))
        if calib is not None:
            hist = getattr(state, "_traj_history_table_m", []) or []
            proj = getattr(state, "_traj_projection_table_m", []) or []
            if hist:
                _draw_polyline_table_m(out, calib, hist, color=(60, 200, 120), thickness=2)
            if proj:
                _draw_polyline_table_m(out, calib, proj, color=(100, 255, 255), thickness=2)

    vp = getattr(state, "_vision_phase", None)
    if vp and vp not in ("unknown", "in_progress"):
        _put_text(out, f"Vision phase: {vp}", (10, 380), (200, 200, 200))

    return out
