#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

M_PER_FT = 0.3048
M_PER_IN = 0.0254
FT2_PER_M2 = 10.7639104167097

TABLE_PRESETS_M: dict[str, tuple[float, float]] = {
    "6ft": (1.829, 0.914),  # 72x36 in playing surface
    "7ft": (1.981, 0.991),
    "8ft": (2.235, 1.118),
    "9ft": (2.84, 1.42),
    "snooker": (3.569, 1.778),
}
TABLE_MENU: list[str] = ["6ft", "7ft", "8ft", "9ft", "snooker"]
UNIT_MENU: list[str] = ["imperial", "metric"]
CORNER_LABELS: list[str] = ["TL", "TR", "BL", "BR"]
SIDE_POCKET_LABELS: list[str] = ["LS", "RS"]

try:
    from edge.calib.table_geometry import auto_calibration_from_corners, table_geometry_dict

    _HAS_EDGE_AUTOCAL = True
except Exception:
    auto_calibration_from_corners = None
    table_geometry_dict = None
    _HAS_EDGE_AUTOCAL = False


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Interactive calibration helper with auto corners and editing. "
            "TL/TR/BL/BR are outside table corners (not pocket centers)."
        ),
    )
    p.add_argument("--frame", type=str, default=None, help="Optional image path to annotate.")
    p.add_argument(
        "--camera",
        type=str,
        default="csi",
        help="Camera source for capture mode: csi, usb, numeric index, or explicit source string.",
    )
    p.add_argument("--usb-index", type=int, default=0)
    p.add_argument("--csi-sensor-id", type=int, default=0)
    p.add_argument("--csi-framerate", "--fps", dest="csi_framerate", type=int, default=30)
    p.add_argument("--csi-flip-method", "--flip", dest="csi_flip_method", type=int, default=0)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    # Table size is selected only via in-window radio UI.
    # Keep CLI non-interactive and camera-focused so automated launches can hand
    # off directly to GUI selection.
    p.add_argument("--units", type=str, default="imperial", choices=["imperial", "metric"])
    p.add_argument("--pocket-radius-m", type=float, default=0.07)
    p.add_argument("--out", type=str, default="/home/$USER/Billiards-AI/calibration.json")
    return p.parse_args()


def _csi_pipeline(sensor_id: int, width: int, height: int, framerate: int, flip_method: int) -> str:
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width=(int){width}, height=(int){height}, "
        f"format=(string)NV12, framerate=(fraction){framerate}/1 ! "
        f"nvvidconv flip-method={flip_method} ! "
        f"video/x-raw, width=(int){width}, height=(int){height}, format=(string)BGRx ! "
        "videoconvert ! video/x-raw, format=(string)BGR ! appsink drop=true max-buffers=1"
    )


def _capture_frame(args: argparse.Namespace) -> np.ndarray:
    cam = str(args.camera).strip().lower()
    use_gst = False
    source: int | str
    if cam == "csi":
        source = _csi_pipeline(
            sensor_id=int(args.csi_sensor_id),
            width=int(args.width),
            height=int(args.height),
            framerate=int(args.csi_framerate),
            flip_method=int(args.csi_flip_method),
        )
        use_gst = True
    elif cam == "usb":
        source = int(args.usb_index)
    elif cam.isdigit():
        source = int(cam)
    else:
        source = str(args.camera)
        if "!" in source or "nvarguscamerasrc" in source:
            use_gst = True

    cap = cv2.VideoCapture(source, cv2.CAP_GSTREAMER if use_gst else 0)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open camera source={source!r}")
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("Failed to capture frame from camera.")
    return frame


def _table_dims_m(table_size: str) -> Tuple[float, float]:
    return TABLE_PRESETS_M[table_size]


def _infer_dims_m_from_payload(payload: dict) -> tuple[float, float] | None:
    length = payload.get("table_length_m")
    width = payload.get("table_width_m")
    if isinstance(length, (int, float)) and isinstance(width, (int, float)) and length > 0 and width > 0:
        return float(length), float(width)
    return None


def _closest_preset(length_m: float, width_m: float) -> str:
    best_name = "9ft"
    best_score = float("inf")
    for name, (preset_l, preset_w) in TABLE_PRESETS_M.items():
        score = abs((length_m - preset_l) / preset_l) + abs((width_m - preset_w) / preset_w)
        if score < best_score:
            best_name = name
            best_score = score
    return best_name


def _detected_default_table_size(out_path: Path) -> str:
    if not out_path.exists():
        return "9ft"
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return "9ft"
    dims = _infer_dims_m_from_payload(payload)
    if dims is None:
        return "9ft"
    return _closest_preset(dims[0], dims[1])


def _table_size_label(size_name: str) -> str:
    return "6ft (bar box)" if size_name == "6ft" else size_name


def _format_dims(length_m: float, width_m: float, units: str) -> str:
    if units == "imperial":
        return f"{length_m / M_PER_FT:.2f} ft x {width_m / M_PER_FT:.2f} ft"
    return f"{length_m:.3f} m x {width_m:.3f} m"


def _estimate_homography(
    image_points: List[Tuple[float, float]],
    table_length_m: float,
    table_width_m: float,
) -> np.ndarray:
    src = np.array(image_points, dtype=np.float64)
    dst = np.array(
        [
            [0.0, 0.0],
            [table_length_m, 0.0],
            [0.0, table_width_m],
            [table_length_m, table_width_m],
        ],
        dtype=np.float64,
    )
    a = []
    for (x, y), (X, Y) in zip(src, dst):
        a.append([-x, -y, -1.0, 0.0, 0.0, 0.0, x * X, y * X, X])
        a.append([0.0, 0.0, 0.0, -x, -y, -1.0, x * Y, y * Y, Y])
    a = np.array(a, dtype=np.float64)
    _, _, vt = np.linalg.svd(a)
    h = vt[-1].reshape(3, 3)
    if abs(float(h[2, 2])) > 1e-12:
        h = h / h[2, 2]
    return h


def _default_corners(h: int, w: int) -> List[Tuple[float, float]]:
    margin_x = 0.12 * w
    margin_y = 0.12 * h
    return [
        (margin_x, margin_y),
        (w - margin_x, margin_y),
        (margin_x, h - margin_y),
        (w - margin_x, h - margin_y),
    ]


def _distance_sq_point_to_rect(px: float, py: float, left: float, top: float, right: float, bottom: float) -> float:
    dx = 0.0
    if px < left:
        dx = left - px
    elif px > right:
        dx = px - right
    dy = 0.0
    if py < top:
        dy = top - py
    elif py > bottom:
        dy = py - bottom
    return dx * dx + dy * dy


def _refine_corner_seeds(gray: np.ndarray, seeds: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    h, w = gray.shape[:2]
    seed_arr = np.array(seeds, dtype=np.float64)
    if seed_arr.shape != (4, 2):
        return [(float(x), float(y)) for x, y in seed_arr]

    features = cv2.goodFeaturesToTrack(
        gray,
        maxCorners=600,
        qualityLevel=0.01,
        minDistance=8,
        blockSize=7,
        useHarrisDetector=False,
    )
    feature_pts = np.empty((0, 2), dtype=np.float64)
    if features is not None:
        feature_pts = features.reshape(-1, 2).astype(np.float64)

    search_radius_sq = float(max(28.0, 0.12 * min(h, w)) ** 2)
    aligned: List[np.ndarray] = []
    for sx, sy in seed_arr:
        best = np.array([sx, sy], dtype=np.float64)
        if feature_pts.shape[0] > 0:
            d = np.sum((feature_pts - np.array([sx, sy], dtype=np.float64)) ** 2, axis=1)
            idx = int(np.argmin(d))
            if float(d[idx]) <= search_radius_sq:
                best = feature_pts[idx]
        aligned.append(best)

    aligned_arr = np.array(aligned, dtype=np.float32).reshape(-1, 1, 2)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
    try:
        cv2.cornerSubPix(gray, aligned_arr, (9, 9), (-1, -1), criteria)
    except cv2.error:
        pass

    refined = aligned_arr.reshape(-1, 2).astype(np.float64)
    refined[:, 0] = np.clip(refined[:, 0], 0.0, float(w - 1))
    refined[:, 1] = np.clip(refined[:, 1], 0.0, float(h - 1))

    min_pair_dist_sq = float("inf")
    for i in range(4):
        for j in range(i + 1, 4):
            d = float(np.sum((refined[i] - refined[j]) ** 2))
            min_pair_dist_sq = min(min_pair_dist_sq, d)
    if min_pair_dist_sq < 25.0:
        return [(float(x), float(y)) for x, y in seed_arr]

    return [(float(x), float(y)) for x, y in refined]


def _estimate_outside_corners(frame: np.ndarray) -> List[Tuple[float, float]]:
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 35, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _default_corners(h, w)

    min_area = 0.12 * float(w * h)
    best_quad: Optional[np.ndarray] = None
    best_quad_area = -1.0

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        area = float(cv2.contourArea(contour))
        if area < min_area:
            continue
        hull = cv2.convexHull(contour).reshape(-1, 2).astype(np.float64)
        if hull.shape[0] < 4:
            continue

        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect).astype(np.float64)
        box = np.array(_order_points_tl_tr_bl_br(box.tolist()), dtype=np.float64)
        snapped = []
        for bx, by in box:
            d = np.sum((hull - np.array([bx, by], dtype=np.float64)) ** 2, axis=1)
            snapped.append(hull[int(np.argmin(d))])
        snapped = np.array(_order_points_tl_tr_bl_br(np.array(snapped, dtype=np.float64).tolist()), dtype=np.float64)
        snapped_area = abs(float(cv2.contourArea(snapped.astype(np.float32))))
        if snapped_area > best_quad_area:
            best_quad_area = snapped_area
            best_quad = snapped

        eps = 0.012 * cv2.arcLength(hull.astype(np.float32), True)
        approx = cv2.approxPolyDP(hull.astype(np.float32), eps, True).reshape(-1, 2).astype(np.float64)
        if approx.shape[0] == 4:
            approx_ordered = np.array(_order_points_tl_tr_bl_br(approx.tolist()), dtype=np.float64)
            approx_area = abs(float(cv2.contourArea(approx_ordered.astype(np.float32))))
            if approx_area > best_quad_area:
                best_quad_area = approx_area
                best_quad = approx_ordered

    if best_quad is None or best_quad_area <= 1.0:
        return _default_corners(h, w)

    refined = _refine_corner_seeds(gray, best_quad.tolist())
    refined_ordered = _order_points_tl_tr_bl_br(refined)
    refined_area = abs(float(cv2.contourArea(np.array(refined_ordered, dtype=np.float32))))
    if refined_area < 0.4 * best_quad_area:
        return [(float(x), float(y)) for x, y in best_quad]
    return refined_ordered


def _order_points_tl_tr_bl_br(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = np.array(points, dtype=np.float64)
    if pts.shape[0] < 4:
        raise ValueError("Need at least 4 points to order corners.")
    s = pts.sum(axis=1)
    diff = pts[:, 0] - pts[:, 1]
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmax(diff)]
    bl = pts[np.argmin(diff)]
    ordered = [tl, tr, bl, br]
    return [(float(p[0]), float(p[1])) for p in ordered]


def _manual_calibration_payload(
    corner_points_px: List[Tuple[float, float]],
    table_length_m: float,
    table_width_m: float,
    pocket_radius_m: float,
    side_pockets_px: Optional[List[Tuple[float, float]]] = None,
) -> dict:
    h = _estimate_homography(corner_points_px, table_length_m, table_width_m)
    if side_pockets_px and len(side_pockets_px) == 2:
        p = np.array([[x, y, 1.0] for x, y in side_pockets_px], dtype=np.float64).T
        q = h @ p
        q[:2, :] /= (q[2:3, :] + 1e-9)
        ls_m = (float(q[0, 0]), float(q[1, 0]))
        rs_m = (float(q[0, 1]), float(q[1, 1]))
    else:
        ls_m = (0.0, table_width_m * 0.5)
        rs_m = (table_length_m, table_width_m * 0.5)
    return {
        "H": [[float(v) for v in row] for row in h.tolist()],
        "pockets": [
            {"label": "top_left_corner", "center_xy_m": [0.0, 0.0], "radius_m": pocket_radius_m},
            {"label": "top_right_corner", "center_xy_m": [table_length_m, 0.0], "radius_m": pocket_radius_m},
            {"label": "bottom_left_corner", "center_xy_m": [0.0, table_width_m], "radius_m": pocket_radius_m},
            {"label": "bottom_right_corner", "center_xy_m": [table_length_m, table_width_m], "radius_m": pocket_radius_m},
            {"label": "left_side_pocket", "center_xy_m": [ls_m[0], ls_m[1]], "radius_m": pocket_radius_m},
            {"label": "right_side_pocket", "center_xy_m": [rs_m[0], rs_m[1]], "radius_m": pocket_radius_m},
        ],
        "table_length_m": table_length_m,
        "table_width_m": table_width_m,
        "kitchen_polygon_xy_m": [
            [0.0, 0.0],
            [table_length_m * 0.25, 0.0],
            [table_length_m * 0.25, table_width_m],
            [0.0, table_width_m],
        ],
        "break_area_polygon_xy_m": [
            [table_length_m * 0.5, 0.0],
            [table_length_m, 0.0],
            [table_length_m, table_width_m],
            [table_length_m * 0.5, table_width_m],
        ],
    }


def main() -> None:
    args = _parse_args()
    out_path = Path(str(args.out)).expanduser()
    detected_default_table_size = _detected_default_table_size(out_path)
    selected_table_size = _detected_default_table_size(out_path)
    selected_units = str(args.units)
    print(
        "Corner meaning: TL/TR/BL/BR are the four outside corners of the table "
        "(cushion intersection corners), not pocket centers."
    )
    print(f"Initial table size preset: {selected_table_size}")
    print(f"Display units: {selected_units}")

    # Backward compatibility for direct invocation snippets on Nano:
    # newer script expects --csi-flip-method, older snippets may pass --flip.
    # argparse already aliases --flip, so nothing else is needed besides keeping
    # this code path explicit and stable.
    if args.frame:
        img = cv2.imread(str(args.frame))
        if img is None:
            raise RuntimeError(f"Failed to read frame image: {args.frame}")
    else:
        img = _capture_frame(args)

    win = "calib-click"
    auto_corner_status = "AUTO corners loaded from frame contour."
    try:
        corner_points: List[Tuple[float, float]] = _estimate_outside_corners(img)
    except Exception as exc:
        h, w = img.shape[:2]
        corner_points = _default_corners(h, w)
        auto_corner_status = f"AUTO corner detect failed ({exc}); using fallback corners."
    print("Auto corners (TL,TR,BL,BR):", json.dumps(corner_points))
    side_pocket_points: List[Tuple[float, float]] = []
    active_point_idx: Optional[int] = None
    dragging = False
    mode = "corners"  # corners or side_pockets
    view = img.copy()

    h_img, w_img = img.shape[:2]
    flip_view_h = False
    flip_view_v = False
    zoom_levels = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]
    zoom_idx = 0
    pan_center_src_x = 0.5 * float(w_img - 1)
    pan_center_src_y = 0.5 * float(h_img - 1)

    header_h = 178
    menu_margin = 20
    menu_padding = 14
    menu_gap = 16
    table_title_gap = 18
    table_row_gap = 24
    units_title_gap = 18
    units_row_gap = 24
    view_title_gap = 18
    view_section_h = 136
    estimated_menu_w = 480
    estimated_menu_h = (
        menu_padding
        + table_title_gap
        + len(TABLE_MENU) * table_row_gap
        + menu_gap
        + units_title_gap
        + len(UNIT_MENU) * units_row_gap
        + menu_gap
        + view_title_gap
        + view_section_h
    )

    row_spacing = 24
    radio_radius = 8
    radio_hit_radius = 12

    def _active_labels() -> List[str]:
        return CORNER_LABELS if mode == "corners" else SIDE_POCKET_LABELS

    def _active_points() -> List[Tuple[float, float]]:
        return corner_points if mode == "corners" else side_pocket_points

    def _set_active_points(points: List[Tuple[float, float]]) -> None:
        nonlocal corner_points, side_pocket_points
        if mode == "corners":
            corner_points = points
        else:
            side_pocket_points = points

    def _current_zoom() -> float:
        return float(zoom_levels[zoom_idx])

    def _source_center_from_oriented(x_oriented: float, y_oriented: float) -> Tuple[float, float]:
        x_src = float(w_img - 1) - x_oriented if flip_view_h else x_oriented
        y_src = float(h_img - 1) - y_oriented if flip_view_v else y_oriented
        return (
            float(np.clip(x_src, 0.0, float(w_img - 1))),
            float(np.clip(y_src, 0.0, float(h_img - 1))),
        )

    def _oriented_center_from_source(x_src: float, y_src: float) -> Tuple[float, float]:
        x_oriented = float(w_img - 1) - x_src if flip_view_h else x_src
        y_oriented = float(h_img - 1) - y_src if flip_view_v else y_src
        return x_oriented, y_oriented

    def _clamp_pan_center() -> None:
        nonlocal pan_center_src_x, pan_center_src_y
        zoom = _current_zoom()
        view_w = float(w_img) / zoom
        view_h = float(h_img) / zoom
        cx_o, cy_o = _oriented_center_from_source(pan_center_src_x, pan_center_src_y)
        if view_w >= float(w_img):
            cx_o = 0.5 * float(w_img - 1)
        else:
            cx_o = float(np.clip(cx_o, 0.5 * view_w, float(w_img) - 0.5 * view_w))
        if view_h >= float(h_img):
            cy_o = 0.5 * float(h_img - 1)
        else:
            cy_o = float(np.clip(cy_o, 0.5 * view_h, float(h_img) - 0.5 * view_h))
        pan_center_src_x, pan_center_src_y = _source_center_from_oriented(cx_o, cy_o)

    def _viewport() -> Tuple[float, float, float, float]:
        _clamp_pan_center()
        zoom = _current_zoom()
        view_w = float(w_img) / zoom
        view_h = float(h_img) / zoom
        cx_o, cy_o = _oriented_center_from_source(pan_center_src_x, pan_center_src_y)
        left = cx_o - 0.5 * view_w
        top = cy_o - 0.5 * view_h
        if view_w < float(w_img):
            left = float(np.clip(left, 0.0, float(w_img) - view_w))
        else:
            left = 0.0
        if view_h < float(h_img):
            top = float(np.clip(top, 0.0, float(h_img) - view_h))
        else:
            top = 0.0
        return left, top, view_w, view_h

    def _source_to_display(x_src: float, y_src: float) -> Tuple[float, float]:
        x_oriented = float(w_img - 1) - x_src if flip_view_h else x_src
        y_oriented = float(h_img - 1) - y_src if flip_view_v else y_src
        left, top, view_w, view_h = _viewport()
        x_disp = (x_oriented - left) * float(w_img) / view_w
        y_disp = (y_oriented - top) * float(h_img) / view_h
        return x_disp, y_disp

    def _display_to_source(x_disp: float, y_disp: float) -> Tuple[float, float]:
        x_disp = float(np.clip(x_disp, 0.0, float(w_img - 1)))
        y_disp = float(np.clip(y_disp, 0.0, float(h_img - 1)))
        left, top, view_w, view_h = _viewport()
        x_oriented = left + (x_disp * view_w / float(w_img))
        y_oriented = top + (y_disp * view_h / float(h_img))
        x_src = float(w_img - 1) - x_oriented if flip_view_h else x_oriented
        y_src = float(h_img - 1) - y_oriented if flip_view_v else y_oriented
        return (
            float(np.clip(x_src, 0.0, float(w_img - 1))),
            float(np.clip(y_src, 0.0, float(h_img - 1))),
        )

    def _render_background() -> np.ndarray:
        if flip_view_h and flip_view_v:
            oriented = cv2.flip(img, -1)
        elif flip_view_h:
            oriented = cv2.flip(img, 1)
        elif flip_view_v:
            oriented = cv2.flip(img, 0)
        else:
            oriented = img
        left, top, view_w, view_h = _viewport()
        sx = float(w_img) / view_w
        sy = float(h_img) / view_h
        m = np.array([[sx, 0.0, -left * sx], [0.0, sy, -top * sy]], dtype=np.float32)
        return cv2.warpAffine(
            oriented,
            m,
            (w_img, h_img),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _nudge_pan(dx_oriented: float, dy_oriented: float) -> None:
        nonlocal pan_center_src_x, pan_center_src_y
        dx_src = -dx_oriented if flip_view_h else dx_oriented
        dy_src = -dy_oriented if flip_view_v else dy_oriented
        pan_center_src_x += dx_src
        pan_center_src_y += dy_src
        _clamp_pan_center()

    def _zoom_step(delta: int, anchor_display_xy: Optional[Tuple[float, float]] = None) -> None:
        nonlocal zoom_idx, pan_center_src_x, pan_center_src_y
        new_idx = int(np.clip(zoom_idx + delta, 0, len(zoom_levels) - 1))
        if new_idx == zoom_idx:
            return
        if anchor_display_xy is None:
            anchor_display_xy = (0.5 * float(w_img - 1), 0.5 * float(h_img - 1))
        anchor_src = _display_to_source(anchor_display_xy[0], anchor_display_xy[1])
        zoom_idx = new_idx
        pan_center_src_x, pan_center_src_y = anchor_src
        _clamp_pan_center()

    def _reset_view() -> None:
        nonlocal flip_view_h, flip_view_v, zoom_idx, pan_center_src_x, pan_center_src_y
        flip_view_h = False
        flip_view_v = False
        zoom_idx = 0
        pan_center_src_x = 0.5 * float(w_img - 1)
        pan_center_src_y = 0.5 * float(h_img - 1)
        _clamp_pan_center()

    def _menu_layout() -> Dict[str, int]:
        safe_w = max(200, w_img - 2 * menu_margin)
        safe_h = max(200, h_img - header_h - menu_margin)
        panel_w = min(estimated_menu_w, safe_w)
        panel_h = min(estimated_menu_h, safe_h)
        default_left = max(menu_margin, w_img - panel_w - menu_margin)
        default_top = max(header_h, h_img - panel_h - menu_margin)
        if len(corner_points) < 4:
            left = default_left
            top = default_top
        else:
            anchors = [
                (menu_margin, header_h),
                (w_img - panel_w - menu_margin, header_h),
                (menu_margin, h_img - panel_h - menu_margin),
                (w_img - panel_w - menu_margin, h_img - panel_h - menu_margin),
                ((w_img - panel_w) // 2, max(header_h, (h_img - panel_h) // 2)),
            ]
            corners_disp = [_source_to_display(float(cx), float(cy)) for cx, cy in corner_points]
            best_anchor = (default_left, default_top)
            best_dist = -1.0
            for ax, ay in anchors:
                left = int(np.clip(ax, menu_margin, max(menu_margin, w_img - panel_w - menu_margin)))
                top = int(np.clip(ay, header_h, max(header_h, h_img - panel_h - menu_margin)))
                right = left + panel_w
                bottom = top + panel_h
                d = min(
                    _distance_sq_point_to_rect(float(cx), float(cy), float(left), float(top), float(right), float(bottom))
                    for cx, cy in corners_disp
                )
                if d > best_dist:
                    best_dist = d
                    best_anchor = (left, top)
            left, top = best_anchor

        table_left = left + menu_padding
        table_top = top + menu_padding + table_title_gap
        units_left = table_left
        units_top = table_top + len(TABLE_MENU) * row_spacing + menu_gap + units_title_gap
        view_left = table_left
        view_top = units_top + len(UNIT_MENU) * row_spacing + menu_gap + view_title_gap
        return {
            "panel_left": left,
            "panel_top": top,
            "panel_w": panel_w,
            "panel_h": panel_h,
            "table_left": table_left,
            "table_top": table_top,
            "units_left": units_left,
            "units_top": units_top,
            "view_left": view_left,
            "view_top": view_top,
        }

    def _view_control_layout(layout: Dict[str, int]) -> Dict[str, Tuple[int, int, int, int] | Tuple[int, int]]:
        view_left = int(layout["view_left"])
        view_top = int(layout["view_top"])
        button_w = 28
        button_h = 20
        pan_size = 20
        flip_h_center = (view_left, view_top)
        flip_v_center = (view_left, view_top + row_spacing)
        zoom_y = view_top + (2 * row_spacing) + 8
        zoom_minus_rect = (view_left, zoom_y - button_h // 2, view_left + button_w, zoom_y + button_h // 2)
        zoom_plus_rect = (
            view_left + button_w + 6,
            zoom_y - button_h // 2,
            view_left + (2 * button_w) + 6,
            zoom_y + button_h // 2,
        )
        pan_origin_y = zoom_y + 16
        pan_up_rect = (view_left + 34, pan_origin_y, view_left + 34 + pan_size, pan_origin_y + pan_size)
        pan_left_rect = (
            view_left + 10,
            pan_origin_y + 24,
            view_left + 10 + pan_size,
            pan_origin_y + 24 + pan_size,
        )
        pan_right_rect = (
            view_left + 58,
            pan_origin_y + 24,
            view_left + 58 + pan_size,
            pan_origin_y + 24 + pan_size,
        )
        pan_down_rect = (
            view_left + 34,
            pan_origin_y + 48,
            view_left + 34 + pan_size,
            pan_origin_y + 48 + pan_size,
        )
        reset_rect = (view_left, pan_origin_y + 76, view_left + 138, pan_origin_y + 100)
        return {
            "flip_h_center": flip_h_center,
            "flip_v_center": flip_v_center,
            "zoom_minus_rect": zoom_minus_rect,
            "zoom_plus_rect": zoom_plus_rect,
            "pan_up_rect": pan_up_rect,
            "pan_left_rect": pan_left_rect,
            "pan_right_rect": pan_right_rect,
            "pan_down_rect": pan_down_rect,
            "reset_rect": reset_rect,
        }

    def _find_nearest_point(x_disp: float, y_disp: float) -> Optional[int]:
        pts = _active_points()
        if not pts:
            return None
        best_i = None
        best_d = float("inf")
        for i, (sx, sy) in enumerate(pts):
            px, py = _source_to_display(float(sx), float(sy))
            d = (px - x_disp) ** 2 + (py - y_disp) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is None:
            return None
        return best_i if best_d <= (22.0**2) else None

    def _draw_radio(
        canvas: np.ndarray,
        x: int,
        y: int,
        selected: bool,
        label: str,
        selected_color: Tuple[int, int, int] = (0, 255, 255),
    ) -> None:
        cv2.circle(canvas, (x, y), radio_radius, (255, 255, 255), 1)
        if selected:
            cv2.circle(canvas, (x, y), radio_radius - 3, selected_color, -1)
        cv2.putText(
            canvas,
            label,
            (x + 16, y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    def _draw_button(canvas: np.ndarray, rect: Tuple[int, int, int, int], label: str) -> None:
        x1, y1, x2, y2 = rect
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (180, 180, 180), 1)
        cv2.putText(
            canvas,
            label,
            (x1 + 7, y2 - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    def _point_in_rect(x: int, y: int, rect: Tuple[int, int, int, int]) -> bool:
        x1, y1, x2, y2 = rect
        return x1 <= x <= x2 and y1 <= y <= y2

    def redraw() -> None:
        nonlocal view
        view = _render_background()
        layout = _menu_layout()

        if len(corner_points) == 4:
            poly_pts = [(_source_to_display(float(x), float(y))) for x, y in corner_points]
            poly = np.array([(int(px), int(py)) for px, py in poly_pts], dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(view, [poly], isClosed=True, color=(0, 200, 255), thickness=1, lineType=cv2.LINE_AA)
        for i, (x_src, y_src) in enumerate(corner_points):
            x, y = _source_to_display(float(x_src), float(y_src))
            cv2.circle(view, (int(x), int(y)), 8, (0, 255, 255), -1)
            cv2.putText(
                view,
                CORNER_LABELS[i],
                (int(x) + 8, int(y) - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
        for i, (x_src, y_src) in enumerate(side_pocket_points):
            x, y = _source_to_display(float(x_src), float(y_src))
            cv2.circle(view, (int(x), int(y)), 6, (255, 200, 0), -1)
            cv2.putText(
                view,
                SIDE_POCKET_LABELS[i],
                (int(x) + 8, int(y) - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 200, 0),
                2,
                cv2.LINE_AA,
            )

        cv2.putText(
            view,
            "Outside-corner mode: drag TL/TR/BL/BR (outside table corners).",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "Mode: m toggles corner<->side-pocket edit | Enter=save | a/r=reset auto-corners | q=quit",
            (20, 54),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "View: h=flip-H | v=flip-V | +/- zoom | arrows or i/j/k/l pan | 0 reset view",
            (20, 78),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "Units: click radio or press t / 6 / 7 | u=undo point in current mode",
            (20, 102),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            auto_corner_status,
            (20, 126),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 255, 180),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            f"Current edit mode: {'outside corners' if mode == 'corners' else 'side pockets'}",
            (20, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255) if mode == "corners" else (255, 200, 0),
            1,
            cv2.LINE_AA,
        )

        panel_left = layout["panel_left"]
        panel_top = layout["panel_top"]
        panel_w = layout["panel_w"]
        panel_h = layout["panel_h"]
        table_left = layout["table_left"]
        table_top = layout["table_top"]
        units_left = layout["units_left"]
        units_top = layout["units_top"]
        view_left = layout["view_left"]
        view_top = layout["view_top"]

        cv2.rectangle(
            view,
            (panel_left, panel_top),
            (panel_left + panel_w, panel_top + panel_h),
            (36, 36, 36),
            -1,
        )
        cv2.rectangle(
            view,
            (panel_left, panel_top),
            (panel_left + panel_w, panel_top + panel_h),
            (150, 150, 150),
            1,
        )

        cv2.putText(
            view,
            "Table size",
            (table_left, table_top - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        for idx, name in enumerate(TABLE_MENU, start=1):
            row_y = table_top + (idx - 1) * row_spacing
            dims = TABLE_PRESETS_M[name]
            marker = " (detected default)" if name == detected_default_table_size else ""
            _draw_radio(
                view,
                table_left,
                row_y,
                selected=(name == selected_table_size),
                label=f"{idx}. {_table_size_label(name)} ({_format_dims(dims[0], dims[1], selected_units)}){marker}",
            )
        cv2.putText(
            view,
            f"Selected table size: {_table_size_label(selected_table_size)}",
            (table_left, table_top + len(TABLE_MENU) * row_spacing + 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

        cv2.putText(
            view,
            "Units",
            (units_left, units_top - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        for idx, unit_name in enumerate(UNIT_MENU, start=1):
            row_y = units_top + (idx - 1) * row_spacing
            _draw_radio(
                view,
                units_left,
                row_y,
                selected=(unit_name == selected_units),
                label=f"Units {idx}. {unit_name}",
                selected_color=(0, 200, 255),
            )

        controls = _view_control_layout(layout)
        cv2.putText(
            view,
            "View",
            (view_left, view_top - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        flip_h_center = controls["flip_h_center"]
        flip_v_center = controls["flip_v_center"]
        _draw_radio(
            view,
            int(flip_h_center[0]),
            int(flip_h_center[1]),
            selected=flip_view_h,
            label="Flip horizontal",
            selected_color=(255, 180, 0),
        )
        _draw_radio(
            view,
            int(flip_v_center[0]),
            int(flip_v_center[1]),
            selected=flip_view_v,
            label="Flip vertical",
            selected_color=(255, 180, 0),
        )

        _draw_button(view, controls["zoom_minus_rect"], "-")
        _draw_button(view, controls["zoom_plus_rect"], "+")
        cv2.putText(
            view,
            f"Zoom: {_current_zoom():.2f}x",
            (view_left + 76, int(flip_v_center[1]) + row_spacing + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

        _draw_button(view, controls["pan_up_rect"], "U")
        _draw_button(view, controls["pan_left_rect"], "L")
        _draw_button(view, controls["pan_right_rect"], "R")
        _draw_button(view, controls["pan_down_rect"], "D")
        cv2.putText(
            view,
            "Pan",
            (view_left + 92, controls["pan_down_rect"][3] - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        _draw_button(view, controls["reset_rect"], "Reset view")

    def _hit_table_option(x: int, y: int) -> Optional[str]:
        layout = _menu_layout()
        table_left = layout["table_left"]
        table_top = layout["table_top"]
        for idx, name in enumerate(TABLE_MENU, start=1):
            row_y = table_top + (idx - 1) * row_spacing
            if abs(x - table_left) <= radio_hit_radius and abs(y - row_y) <= radio_hit_radius:
                return name
        return None

    def _hit_units_option(x: int, y: int) -> Optional[str]:
        layout = _menu_layout()
        units_left = layout["units_left"]
        units_top = layout["units_top"]
        for idx, name in enumerate(UNIT_MENU, start=1):
            row_y = units_top + (idx - 1) * row_spacing
            if abs(x - units_left) <= radio_hit_radius and abs(y - row_y) <= radio_hit_radius:
                return name
        return None

    def _hit_view_control(x: int, y: int) -> Optional[str]:
        layout = _menu_layout()
        controls = _view_control_layout(layout)
        flip_h_center = controls["flip_h_center"]
        flip_v_center = controls["flip_v_center"]
        if abs(x - int(flip_h_center[0])) <= radio_hit_radius and abs(y - int(flip_h_center[1])) <= radio_hit_radius:
            return "flip_h"
        if abs(x - int(flip_v_center[0])) <= radio_hit_radius and abs(y - int(flip_v_center[1])) <= radio_hit_radius:
            return "flip_v"
        if _point_in_rect(x, y, controls["zoom_minus_rect"]):
            return "zoom_out"
        if _point_in_rect(x, y, controls["zoom_plus_rect"]):
            return "zoom_in"
        if _point_in_rect(x, y, controls["pan_up_rect"]):
            return "pan_up"
        if _point_in_rect(x, y, controls["pan_left_rect"]):
            return "pan_left"
        if _point_in_rect(x, y, controls["pan_right_rect"]):
            return "pan_right"
        if _point_in_rect(x, y, controls["pan_down_rect"]):
            return "pan_down"
        if _point_in_rect(x, y, controls["reset_rect"]):
            return "view_reset"
        return None

    def on_mouse(event, x, y, _flags, _userdata) -> None:
        nonlocal selected_table_size, selected_units, active_point_idx, dragging, flip_view_h, flip_view_v
        if event == cv2.EVENT_LBUTTONDOWN:
            idx = _find_nearest_point(float(x), float(y))
            if idx is not None:
                active_point_idx = idx
                dragging = True
                return

            hit_table = _hit_table_option(x, y)
            if hit_table is not None:
                selected_table_size = hit_table
                redraw()
                return
            hit_units = _hit_units_option(x, y)
            if hit_units is not None:
                selected_units = hit_units
                redraw()
                return
            hit_view = _hit_view_control(x, y)
            if hit_view is not None:
                if hit_view == "flip_h":
                    flip_view_h = not flip_view_h
                    _clamp_pan_center()
                elif hit_view == "flip_v":
                    flip_view_v = not flip_view_v
                    _clamp_pan_center()
                elif hit_view == "zoom_in":
                    _zoom_step(+1)
                elif hit_view == "zoom_out":
                    _zoom_step(-1)
                elif hit_view == "pan_up":
                    _, _, view_w, view_h = _viewport()
                    _nudge_pan(0.0, -0.10 * view_h)
                elif hit_view == "pan_left":
                    _, _, view_w, view_h = _viewport()
                    _nudge_pan(-0.10 * view_w, 0.0)
                elif hit_view == "pan_right":
                    _, _, view_w, view_h = _viewport()
                    _nudge_pan(+0.10 * view_w, 0.0)
                elif hit_view == "pan_down":
                    _, _, view_w, view_h = _viewport()
                    _nudge_pan(0.0, +0.10 * view_h)
                elif hit_view == "view_reset":
                    _reset_view()
                redraw()
                return

            pts = _active_points()
            labels = _active_labels()
            if len(pts) < len(labels):
                src_x, src_y = _display_to_source(float(x), float(y))
                pts.append((src_x, src_y))
                _set_active_points(pts)
                redraw()
        elif event == cv2.EVENT_MOUSEMOVE and dragging and active_point_idx is not None:
            pts = _active_points()
            if 0 <= active_point_idx < len(pts):
                src_x, src_y = _display_to_source(float(x), float(y))
                pts[active_point_idx] = (src_x, src_y)
                _set_active_points(pts)
                redraw()
        elif event == cv2.EVENT_LBUTTONUP:
            dragging = False
            active_point_idx = None

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_mouse)
    redraw()

    while True:
        cv2.imshow(win, view)
        key = cv2.waitKey(20) & 0xFF
        if key in (ord("q"), 27):
            cv2.destroyAllWindows()
            print("Cancelled.", file=sys.stderr)
            raise SystemExit(1)
        if key in (ord("r"), ord("a")):
            corner_points = _estimate_outside_corners(img)
            side_pocket_points = []
            auto_corner_status = "AUTO corners reloaded from frame contour."
            redraw()
        if key in (ord("m"),):
            mode = "side_pockets" if mode == "corners" else "corners"
            redraw()
        if key in (ord("u"),):
            pts = _active_points()
            if pts:
                pts.pop()
                _set_active_points(pts)
                redraw()
        if key in (ord("t"),):
            selected_units = "metric" if selected_units == "imperial" else "imperial"
            redraw()
        if key in (ord("1"), ord("2"), ord("3"), ord("4"), ord("5")):
            idx = int(chr(key)) - 1
            if 0 <= idx < len(TABLE_MENU):
                selected_table_size = TABLE_MENU[idx]
                redraw()
        if key in (ord("6"), ord("7")):
            idx = int(chr(key)) - 6
            if 0 <= idx < len(UNIT_MENU):
                selected_units = UNIT_MENU[idx]
                redraw()
        if key in (ord("h"),):
            flip_view_h = not flip_view_h
            _clamp_pan_center()
            redraw()
        if key in (ord("v"),):
            flip_view_v = not flip_view_v
            _clamp_pan_center()
            redraw()
        if key in (ord("0"),):
            _reset_view()
            redraw()
        if key in (ord("+"), ord("="), ord("]")):
            _zoom_step(+1)
            redraw()
        if key in (ord("-"), ord("_"), ord("[")):
            _zoom_step(-1)
            redraw()
        if key in (81, ord("j")):  # left arrow or j
            _, _, view_w, _ = _viewport()
            _nudge_pan(-0.08 * view_w, 0.0)
            redraw()
        if key in (83, ord("l")):  # right arrow or l
            _, _, view_w, _ = _viewport()
            _nudge_pan(+0.08 * view_w, 0.0)
            redraw()
        if key in (82, ord("i")):  # up arrow or i
            _, _, _, view_h = _viewport()
            _nudge_pan(0.0, -0.08 * view_h)
            redraw()
        if key in (84, ord("k")):  # down arrow or k
            _, _, _, view_h = _viewport()
            _nudge_pan(0.0, +0.08 * view_h)
            redraw()
        if key in (13, 10):
            if len(corner_points) != 4:
                print("Need exactly 4 outside corner points before saving.")
                continue
            if len(side_pocket_points) not in (0, 2):
                print("Side pockets: set none or exactly 2 points (LS, RS).")
                continue
            break

    cv2.destroyAllWindows()

    table_length_m, table_width_m = _table_dims_m(selected_table_size)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_with_edge_helpers = False

    if _HAS_EDGE_AUTOCAL and len(side_pocket_points) == 0:
        try:
            calib, geom = auto_calibration_from_corners(
                image_points=corner_points,
                table_length_m=table_length_m,
                table_width_m=table_width_m,
                pocket_radius_m=float(args.pocket_radius_m),
            )
            calib.save(str(out_path))
            print(json.dumps(table_geometry_dict(geom), indent=2))
            wrote_with_edge_helpers = True
        except Exception:
            wrote_with_edge_helpers = False

    if not wrote_with_edge_helpers:
        payload = _manual_calibration_payload(
            corner_points_px=corner_points,
            table_length_m=table_length_m,
            table_width_m=table_width_m,
            pocket_radius_m=float(args.pocket_radius_m),
            side_pockets_px=side_pocket_points if len(side_pocket_points) == 2 else None,
        )
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    area_m2 = table_length_m * table_width_m
    if selected_units == "imperial":
        print(
            f"Wrote calibration: {out_path}\n"
            f"Table size: {_table_size_label(selected_table_size)} "
            f"({table_length_m / M_PER_FT:.2f} ft x {table_width_m / M_PER_FT:.2f} ft, "
            f"{area_m2 * FT2_PER_M2:.2f} ft^2)"
        )
    else:
        print(
            f"Wrote calibration: {out_path}\n"
            f"Table size: {_table_size_label(selected_table_size)} "
            f"({table_length_m:.3f} m x {table_width_m:.3f} m, {area_m2:.3f} m^2)"
        )
    print("Outside corners (TL,TR,BL,BR):", json.dumps(corner_points))
    if side_pocket_points:
        print("Side pockets (LS,RS) pixel points:", json.dumps(side_pocket_points))
    if not wrote_with_edge_helpers:
        print("Saved using standalone calibration writer.")


if __name__ == "__main__":
    main()
