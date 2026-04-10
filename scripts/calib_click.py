#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
TABLE_SIZE_ALIASES: dict[str, str] = {
    "bar_box": "6ft",
    "bar_box_6ft": "6ft",
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
    p.add_argument(
        "--table-size",
        type=str,
        default="auto",
        choices=["auto", "6ft", "bar_box", "bar_box_6ft", "7ft", "8ft", "9ft", "snooker"],
        help="Table preset. Use 'auto' to use detected default with editable radio list.",
    )
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


def _initial_table_size(arg_table_size: str, out_path: Path) -> str:
    if arg_table_size != "auto":
        return TABLE_SIZE_ALIASES.get(arg_table_size, arg_table_size)
    return _detected_default_table_size(out_path)


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


def _estimate_outside_corners(frame: np.ndarray) -> List[Tuple[float, float]]:
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        margin_x = 0.12 * w
        margin_y = 0.12 * h
        return [
            (margin_x, margin_y),
            (w - margin_x, margin_y),
            (margin_x, h - margin_y),
            (w - margin_x, h - margin_y),
        ]
    largest = max(contours, key=cv2.contourArea)
    eps = 0.02 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, eps, True)
    pts = approx.reshape(-1, 2).astype(np.float64)
    if len(pts) < 4:
        x, y, bw, bh = cv2.boundingRect(largest)
        pts = np.array([[x, y], [x + bw, y], [x, y + bh], [x + bw, y + bh]], dtype=np.float64)
    if len(pts) > 4:
        hull = cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2).astype(np.float64)
        if len(hull) >= 4:
            best = None
            best_area = -1.0
            n = len(hull)
            for i in range(n):
                for j in range(i + 1, n):
                    for k in range(j + 1, n):
                        for l in range(k + 1, n):
                            quad = np.array([hull[i], hull[j], hull[k], hull[l]], dtype=np.float64)
                            area = abs(cv2.contourArea(quad.astype(np.float32)))
                            if area > best_area:
                                best_area = area
                                best = quad
            if best is not None:
                pts = best
    return _order_points_tl_tr_bl_br(pts.tolist())


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
    selected_table_size = _initial_table_size(str(args.table_size), out_path)
    selected_units = str(args.units)
    print(
        "Corner meaning: TL/TR/BL/BR are the four outside corners of the table "
        "(cushion intersection corners), not pocket centers."
    )
    print(f"Initial table size preset: {selected_table_size}")
    print(f"Display units: {selected_units}")

    if args.frame:
        img = cv2.imread(str(args.frame))
        if img is None:
            raise RuntimeError(f"Failed to read frame image: {args.frame}")
    else:
        img = _capture_frame(args)

    win = "calib-click"
    corner_points: List[Tuple[float, float]] = _estimate_outside_corners(img)
    side_pocket_points: List[Tuple[float, float]] = []
    active_point_idx: Optional[int] = None
    dragging = False
    mode = "corners"  # corners or side_pockets
    view = img.copy()

    table_left = 20
    table_top = 92
    row_spacing = 24
    radio_radius = 8
    radio_hit_radius = 12
    units_left = 20
    units_top = table_top + len(TABLE_MENU) * row_spacing + 40

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

    def _find_nearest_point(x: float, y: float) -> Optional[int]:
        pts = _active_points()
        if not pts:
            return None
        best_i = None
        best_d = float("inf")
        for i, (px, py) in enumerate(pts):
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is None:
            return None
        return best_i if best_d <= (20.0**2) else None

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

    def redraw() -> None:
        nonlocal view
        view = img.copy()

        for i, (x, y) in enumerate(corner_points):
            cv2.circle(view, (int(x), int(y)), 6, (0, 255, 255), -1)
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
        for i, (x, y) in enumerate(side_pocket_points):
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
            "Mode: m toggles corner<->side-pocket edit | Enter=save | r=reset auto-corners | q=quit",
            (20, 54),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "Units: click radio or press t / 6 / 7 | u=undo point in current mode",
            (20, 76),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            f"Current edit mode: {'outside corners' if mode == 'corners' else 'side pockets'}",
            (20, 98),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255) if mode == "corners" else (255, 200, 0),
            1,
            cv2.LINE_AA,
        )

        for idx, name in enumerate(TABLE_MENU, start=1):
            row_y = table_top + 24 + (idx - 1) * row_spacing
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
            (20, table_top + len(TABLE_MENU) * row_spacing + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
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

    def _hit_table_option(x: int, y: int) -> Optional[str]:
        for idx, name in enumerate(TABLE_MENU, start=1):
            row_y = table_top + 24 + (idx - 1) * row_spacing
            if abs(x - table_left) <= radio_hit_radius and abs(y - row_y) <= radio_hit_radius:
                return name
        return None

    def _hit_units_option(x: int, y: int) -> Optional[str]:
        for idx, name in enumerate(UNIT_MENU, start=1):
            row_y = units_top + (idx - 1) * row_spacing
            if abs(x - units_left) <= radio_hit_radius and abs(y - row_y) <= radio_hit_radius:
                return name
        return None

    def on_mouse(event, x, y, _flags, _userdata) -> None:
        nonlocal selected_table_size, selected_units, active_point_idx, dragging
        if event == cv2.EVENT_LBUTTONDOWN:
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
            idx = _find_nearest_point(float(x), float(y))
            if idx is not None:
                active_point_idx = idx
                dragging = True
                return
            pts = _active_points()
            labels = _active_labels()
            if len(pts) < len(labels):
                pts.append((float(x), float(y)))
                _set_active_points(pts)
                redraw()
        elif event == cv2.EVENT_MOUSEMOVE and dragging and active_point_idx is not None:
            pts = _active_points()
            if 0 <= active_point_idx < len(pts):
                pts[active_point_idx] = (float(x), float(y))
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
        if key == ord("r"):
            corner_points = _estimate_outside_corners(img)
            side_pocket_points = []
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
