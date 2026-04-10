#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

try:
    from edge.calib.table_geometry import auto_calibration_from_corners, table_geometry_dict

    _HAS_EDGE_AUTOCAL = True
except Exception:
    auto_calibration_from_corners = None
    table_geometry_dict = None
    _HAS_EDGE_AUTOCAL = False

TABLE_PRESETS: dict[str, tuple[float, float]] = {
    "7ft": (1.981, 0.991),
    "8ft": (2.235, 1.118),
    "9ft": (2.84, 1.42),
    "snooker": (3.569, 1.778),
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Interactive 4-corner calibration helper (TL, TR, BL, BR).",
    )
    p.add_argument(
        "--frame",
        type=str,
        default=None,
        help="Optional image path to annotate. If omitted, capture one frame from camera.",
    )
    p.add_argument(
        "--camera",
        type=str,
        default="csi",
        help="Camera source for capture mode: csi, usb, numeric index, or explicit source string.",
    )
    p.add_argument("--usb-index", type=int, default=0)
    p.add_argument("--csi-sensor-id", type=int, default=0)
    p.add_argument(
        "--csi-framerate",
        "--fps",
        dest="csi_framerate",
        type=int,
        default=30,
        help="CSI framerate (legacy alias: --fps)",
    )
    p.add_argument(
        "--csi-flip-method",
        "--flip",
        dest="csi_flip_method",
        type=int,
        default=0,
        help="CSI nvvidconv flip-method (legacy alias: --flip)",
    )
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument(
        "--table-size",
        type=str,
        default="auto",
        choices=["auto", "7ft", "8ft", "9ft", "snooker"],
        help="Table preset. Use 'auto' to show a menu with detected default.",
    )
    p.add_argument("--pocket-radius-m", type=float, default=0.07)
    p.add_argument(
        "--out",
        type=str,
        default="/home/$USER/Billiards-AI/calibration.json",
        help="Output calibration path",
    )
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


def _capture_frame(args: argparse.Namespace):
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


def _table_dims(table_size: str) -> Tuple[float, float]:
    return TABLE_PRESETS[table_size]


def _infer_dims_from_payload(payload: dict) -> tuple[float, float] | None:
    length = payload.get("table_length_m")
    width = payload.get("table_width_m")
    if isinstance(length, (int, float)) and isinstance(width, (int, float)) and length > 0 and width > 0:
        return float(length), float(width)
    return None


def _closest_preset(length_m: float, width_m: float) -> str:
    best_name = "9ft"
    best_score = float("inf")
    for name, (preset_l, preset_w) in TABLE_PRESETS.items():
        # Relative error is more stable across scales than absolute deltas.
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
    dims = _infer_dims_from_payload(payload)
    if dims is None:
        return "9ft"
    return _closest_preset(dims[0], dims[1])


def _choose_table_size(arg_table_size: str, out_path: Path) -> str:
    if arg_table_size != "auto":
        return arg_table_size

    detected_default = _detected_default_table_size(out_path)
    menu = ["7ft", "8ft", "9ft", "snooker"]
    default_idx = menu.index(detected_default) + 1

    if not sys.stdin.isatty():
        print(f"Auto-selected table size: {detected_default} (non-interactive mode)")
        return detected_default

    print("\nSelect table size preset (default is detected from existing calibration):")
    for idx, name in enumerate(menu, start=1):
        marker = " (detected default)" if name == detected_default else ""
        dims = TABLE_PRESETS[name]
        print(f"  {idx}) {name} ({dims[0]:.3f}m x {dims[1]:.3f}m){marker}")
    raw = input(f"Enter choice [1-{len(menu)}] (default {default_idx}): ").strip()
    if not raw:
        return detected_default
    if raw.isdigit():
        sel = int(raw)
        if 1 <= sel <= len(menu):
            return menu[sel - 1]
    if raw in menu:
        return raw
    print(f"Invalid selection {raw!r}; using detected default {detected_default}.")
    return detected_default


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


def _manual_calibration_payload(
    image_points: List[Tuple[float, float]],
    table_length_m: float,
    table_width_m: float,
    pocket_radius_m: float,
) -> dict:
    h = _estimate_homography(image_points, table_length_m, table_width_m)
    return {
        "H": [[float(v) for v in row] for row in h.tolist()],
        "pockets": [
            {"label": "top_left_corner", "center_xy_m": [0.0, 0.0], "radius_m": pocket_radius_m},
            {"label": "top_right_corner", "center_xy_m": [table_length_m, 0.0], "radius_m": pocket_radius_m},
            {"label": "bottom_left_corner", "center_xy_m": [0.0, table_width_m], "radius_m": pocket_radius_m},
            {
                "label": "bottom_right_corner",
                "center_xy_m": [table_length_m, table_width_m],
                "radius_m": pocket_radius_m,
            },
            {"label": "left_side_pocket", "center_xy_m": [0.0, table_width_m * 0.5], "radius_m": pocket_radius_m},
            {
                "label": "right_side_pocket",
                "center_xy_m": [table_length_m, table_width_m * 0.5],
                "radius_m": pocket_radius_m,
            },
        ],
        # Additional keys are ignored by older loaders and used by newer ones.
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
    selected_table_size = _choose_table_size(str(args.table_size), out_path)
    print(
        "Corner meaning: TL/TR/BL/BR are the four table cloth corners "
        "(cushion intersections), not pocket centers."
    )
    print(f"Using table size preset: {selected_table_size}")

    if args.frame:
        img = cv2.imread(str(args.frame))
        if img is None:
            raise RuntimeError(f"Failed to read frame image: {args.frame}")
    else:
        img = _capture_frame(args)

    win = "calib-click"
    points: List[Tuple[float, float]] = []
    labels = ["TL", "TR", "BL", "BR"]
    view = img.copy()

    def redraw() -> None:
        nonlocal view
        view = img.copy()
        for i, (x, y) in enumerate(points):
            cv2.circle(view, (int(x), int(y)), 6, (0, 255, 255), -1)
            cv2.putText(
                view,
                labels[i],
                (int(x) + 8, int(y) - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
        if len(points) < 4:
            prompt = f"Click {labels[len(points)]} cloth corner (not pocket center)"
        else:
            prompt = "Press Enter to save, r to reset, q to quit"
        cv2.putText(view, prompt, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(
            view,
            "Order: TL=top-left, TR=top-right, BL=bottom-left, BR=bottom-right",
            (20, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    def on_mouse(event, x, y, _flags, _userdata) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if len(points) >= 4:
            return
        points.append((float(x), float(y)))
        redraw()

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
            points.clear()
            redraw()
        if key in (13, 10):
            if len(points) != 4:
                continue
            break

    cv2.destroyAllWindows()

    L, W = _table_dims(selected_table_size)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_with_edge_helpers = False
    if _HAS_EDGE_AUTOCAL:
        try:
            calib, geom = auto_calibration_from_corners(
                image_points=points,
                table_length_m=L,
                table_width_m=W,
                pocket_radius_m=float(args.pocket_radius_m),
            )
            calib.save(str(out_path))
            print(json.dumps(table_geometry_dict(geom), indent=2))
            wrote_with_edge_helpers = True
        except Exception:
            wrote_with_edge_helpers = False
    if not wrote_with_edge_helpers:
        payload = _manual_calibration_payload(
            image_points=points,
            table_length_m=L,
            table_width_m=W,
            pocket_radius_m=float(args.pocket_radius_m),
        )
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    print(f"Wrote calibration: {out_path}")
    print("Corners (TL,TR,BL,BR):", json.dumps(points))
    print(f"Table size preset: {selected_table_size}")
    if not wrote_with_edge_helpers:
        print("Saved using standalone calibration writer fallback.")


if __name__ == "__main__":
    main()

