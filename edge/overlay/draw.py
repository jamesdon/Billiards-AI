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


def _projector_pixel_span(calib: Calibration) -> Optional[Tuple[float, float, float, float]]:
    """Axis-aligned bounds in projector pixels for the table rectangle (0,0)-(L,W)."""
    hp = calib.H_projector
    if hp is None:
        return None
    L, W = float(calib.table_length_m), float(calib.table_width_m)
    xs: list[float] = []
    ys: list[float] = []
    # Match `table_geometry` pocket frame: head rail x=0, y across width W.
    for xy in ((0.0, 0.0), (0.0, W), (L, 0.0), (L, W)):
        px, py = hp.to_pixel(xy)
        xs.append(float(px))
        ys.append(float(py))
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    if maxx - minx < 1e-6 or maxy - miny < 1e-6:
        return None
    return (minx, miny, maxx, maxy)


def _table_m_to_projector_panel_xy(
    xy_m: Tuple[float, float],
    calib: Calibration,
    span: Tuple[float, float, float, float],
    pw: int,
    ph: int,
    margin: int = 3,
) -> Tuple[int, int]:
    hp = calib.H_projector
    assert hp is not None
    minx, miny, maxx, maxy = span
    spanx = maxx - minx
    spany = maxy - miny
    px, py = hp.to_pixel(xy_m)
    u = (px - minx) / spanx * (pw - 2 * margin) + margin
    v = (py - miny) / spany * (ph - 2 * margin) + margin
    return int(np.clip(u, 0, pw - 1)), int(np.clip(v, 0, ph - 1))


def _panel_polyline(
    poly_m: List[Tuple[float, float]],
    calib: Calibration,
    span: Tuple[float, float, float, float],
    pw: int,
    ph: int,
) -> Optional[np.ndarray]:
    if len(poly_m) < 2:
        return None
    pts = [_table_m_to_projector_panel_xy(xy, calib, span, pw, ph) for xy in poly_m]
    return np.array([pts], dtype=np.int32)


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


def _draw_projector_mirror_inset(out: np.ndarray, state: GameState, calib: Calibration) -> None:
    """Top-right inset: same table overlays in projector pixel space (requires ``H_projector``)."""
    if calib.H_projector is None:
        return
    layers = state.projector_layers
    want = state.trajectory_assist_enabled or any(
        [
            layers.show_break_box and bool(calib.break_area_polygon_xy_m),
            layers.show_break_string and len(calib.kitchen_polygon_xy_m) >= 2,
            layers.show_best_next_shot,
            layers.show_alt_next_shot,
        ]
    )
    if not want:
        return
    span = _projector_pixel_span(calib)
    if span is None:
        return
    fh, fw = int(out.shape[0]), int(out.shape[1])
    pw = int(min(280, max(160, fw // 4)))
    minx, miny, maxx, maxy = span
    spanx = maxx - minx
    spany = maxy - miny
    ph = int(np.clip(pw * spany / (spanx + 1e-9) * 0.55, 90.0, float(fh // 3)))
    panel = np.full((ph, pw, 3), 28, dtype=np.uint8)

    def draw_on_panel(poly_m: List[Tuple[float, float]], color: Tuple[int, int, int], closed: bool) -> None:
        arr = _panel_polyline(poly_m, calib, span, pw, ph)
        if arr is None:
            return
        cv2.polylines(panel, arr, isClosed=closed, color=color, thickness=2, lineType=cv2.LINE_AA)

    if layers.show_break_box and calib.break_area_polygon_xy_m:
        draw_on_panel(list(calib.break_area_polygon_xy_m), (0, 255, 255), True)
    if layers.show_break_string and len(calib.kitchen_polygon_xy_m) >= 2:
        draw_on_panel(list(calib.kitchen_polygon_xy_m[:2]), (0, 200, 255), False)
    if layers.show_best_next_shot:
        hb = getattr(state, "_hint_best_table_m", []) or []
        if hb:
            draw_on_panel(hb, (80, 220, 80), False)
    if layers.show_alt_next_shot:
        ha = getattr(state, "_hint_alt_table_m", []) or []
        if ha:
            draw_on_panel(ha, (200, 100, 255), False)
    if state.trajectory_assist_enabled:
        hist = getattr(state, "_traj_history_table_m", []) or []
        proj = getattr(state, "_traj_projection_table_m", []) or []
        if hist:
            draw_on_panel(hist, (60, 200, 120), False)
        if proj:
            draw_on_panel(proj, (100, 255, 255), False)

    x0, y0 = fw - pw - 6, 6
    out[y0 : y0 + ph, x0 : x0 + pw] = panel
    cv2.rectangle(out, (x0, y0), (x0 + pw - 1, y0 + ph - 1), (180, 180, 180), 1, cv2.LINE_AA)
    _put_text(out, "Projector", (x0 + 4, y0 + 16), (220, 220, 220))


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

    if calib is not None:
        _draw_projector_mirror_inset(out, state, calib)

    return out
