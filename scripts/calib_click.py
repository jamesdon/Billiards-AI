#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

import cv2

from edge.calib.table_geometry import auto_calibration_from_corners, table_geometry_dict


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
        default="9ft",
        choices=["7ft", "8ft", "9ft", "snooker"],
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
    presets = {
        "7ft": (1.981, 0.991),
        "8ft": (2.235, 1.118),
        "9ft": (2.84, 1.42),
        "snooker": (3.569, 1.778),
    }
    return presets[table_size]


def main() -> None:
    args = _parse_args()

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
            prompt = f"Click {labels[len(points)]} corner"
        else:
            prompt = "Press Enter to save, r to reset, q to quit"
        cv2.putText(view, prompt, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

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

    L, W = _table_dims(str(args.table_size))
    calib, geom = auto_calibration_from_corners(
        image_points=points,
        table_length_m=L,
        table_width_m=W,
        pocket_radius_m=float(args.pocket_radius_m),
    )
    out_path = Path(str(args.out)).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    calib.save(str(out_path))
    print(f"Wrote calibration: {out_path}")
    print("Corners (TL,TR,BL,BR):", json.dumps(points))
    print(json.dumps(table_geometry_dict(geom), indent=2))


if __name__ == "__main__":
    main()

