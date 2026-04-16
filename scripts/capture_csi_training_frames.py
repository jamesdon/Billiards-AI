#!/usr/bin/env python3
"""
Save frames from the Jetson-family CSI camera (same GStreamer path as edge.main) for YOLO labeling.

Training still runs on image files + .txt labels; this tool only fills the images/ side from live view.
Run from repo root:  python scripts/capture_csi_training_frames.py --help
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from edge.io.camera_opencv import (  # noqa: E402
    OpenCVCamera,
    jetson_csi_gstreamer_pipeline,
    opencv_gstreamer_enabled,
)

try:
    import cv2
except ImportError as exc:  # pragma: no cover
    raise SystemExit("OpenCV (cv2) is required.") from exc


def main() -> None:
    ap = argparse.ArgumentParser(description="Capture frames from CSI for YOLO dataset building.")
    ap.add_argument(
        "--out-dir",
        type=str,
        default="data/datasets/billiards/images/capture",
        help="Directory to write JPEGs (created if missing). Default under dataset tree.",
    )
    ap.add_argument("--count", type=int, default=200, help="Stop after this many saved frames.")
    ap.add_argument(
        "--stride",
        type=int,
        default=15,
        help="Save one frame every N frames from the stream (reduces near-duplicates).",
    )
    ap.add_argument("--prefix", type=str, default="live", help="Filename prefix: {prefix}_{idx:06d}.jpg")
    ap.add_argument("--csi-sensor-id", type=int, default=0)
    ap.add_argument("--csi-flip-method", type=int, default=0)
    ap.add_argument("--csi-framerate", type=int, default=30)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()

    if not opencv_gstreamer_enabled():
        raise SystemExit(
            "OpenCV must be built with GStreamer for CSI. On L4T use distro python3-opencv "
            "and a venv with --system-site-packages (see docs/ORIN_NANO_TRAIN_AND_TEST.md)."
        )

    out = (_REPO / args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    pipeline = jetson_csi_gstreamer_pipeline(
        sensor_id=int(args.csi_sensor_id),
        capture_width=int(args.width),
        capture_height=int(args.height),
        display_width=int(args.width),
        display_height=int(args.height),
        framerate=int(args.csi_framerate),
        flip_method=int(args.csi_flip_method),
    )
    cam = OpenCVCamera(source=pipeline, width=args.width, height=args.height, use_gstreamer=True)

    saved = 0
    seen = 0
    stride = max(1, int(args.stride))
    for _ts, frame in cam.frames():
        seen += 1
        if seen != 1 and (seen % stride) != 0:
            continue
        path = out / f"{args.prefix}_{saved:06d}.jpg"
        cv2.imwrite(str(path), frame)
        saved += 1
        print(path)
        if saved >= int(args.count):
            break

    print(f"Wrote {saved} frames under {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
