#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Running `python scripts/calib_click.py` puts only `scripts/` on sys.path, so `import edge` fails
# unless the project root (parent of `scripts/`) is on the path.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import cv2
    import numpy as np
except Exception:
    print(
        "Failed to import cv2/numpy. On Jetson-family devices this usually means a NumPy/OpenCV ABI mismatch.\n"
        "Fix by running:\n"
        "  cd \"/home/$USER/Billiards-AI\"\n"
        "  source \"/home/$USER/Billiards-AI/.venv/bin/activate\"\n"
        "  export PYTHONNOUSERSITE=1\n"
        "  python -m pip install --upgrade --force-reinstall \"numpy<2\"\n"
        "Then rerun calibration with:\n"
        "  /home/$USER/Billiards-AI/scripts/start_calibration.sh",
        file=sys.stderr,
    )
    raise

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
# Physical TL,TR,BL,BR — place on the table at each corner pocket’s **inner throat**:
# the point where the two *playing-surface* rail lines (long rail × short rail) would
# meet if extended into the pocket (not pocket center, not outer cushion nose).
CORNER_LABELS: list[str] = ["TL", "TR", "BL", "BR"]
# corner_points[i] is always physical i; polylines must follow the table perimeter, not 0,1,2,3.
CORNER_OUTLINE_INDEX: tuple[int, ...] = (0, 1, 3, 2)  # TL → TR → BR → BL

_JETSON_CSI_HINT = (
    "Jetson-family CSI / Argus (nvarguscamerasrc) often prints 'Failed to create CaptureSession' when no frame arrives.\n"
    "Try, in order:\n"
    "  • Close other camera users (another calib_click, edge.main, nvgstcapture). Then:\n"
    "      sudo systemctl restart nvargus-daemon\n"
    "    (service name can differ slightly by L4T; reboot if Argus stays wedged.)\n"
    "  • Wrong module index: CSI_SENSOR_ID=1 bash scripts/start_calibration.sh\n"
    "  • Wrong orientation: CSI_FLIP_METHOD=0 bash scripts/start_calibration.sh (also try 2 or 6)\n"
    "  • Lighter CSI mode (extra args after start_calibration.sh; last flags win):\n"
    "      bash scripts/start_calibration.sh --width 640 --height 480 --csi-framerate 15\n"
    "  • V4L2 instead of the nvargus GStreamer string (often /dev/video0 on Jetson):\n"
    "      bash scripts/start_calibration.sh --camera 0\n"
    "  • Sanity-check Argus outside OpenCV (adjust sensor-id / caps as needed):\n"
    "      gst-launch-1.0 nvarguscamerasrc sensor-id=0 num-buffers=1 ! nvvidconv ! xvimagesink\n"
    "  • If nvarguscamerasrc prints **No cameras available**: Argus sees no CSI module.\n"
    "      Re-seat the ribbon cable (correct side/orientation), try sensor-id=1, check\n"
    "      `sudo dmesg | grep -iE 'imx|tegracam|nv_camera'` after a cold boot.\n"
    "      If it used to work unchanged: JetPack/L4T updates, overlays, or power mode can\n"
    "      drop enumeration—try cold boot, `sudo systemctl restart nvargus-daemon`,\n"
    "      `bash scripts/jetson_csi_setup.sh`, and compare kernel/JetPack to a known-good image.\n"
    "  • USB fallback only helps if a UVC device exists: `ls /dev/video*` — use `--camera csi` for CSI.\n"
    "  • If you pass `--width 640` but the error text still shows 1280x720, `git pull`\n"
    "      so `start_calibration.sh` includes forwarding of extra args to calib_click.py.\n"
)


def _csi_troubleshoot_footer(args: argparse.Namespace) -> str:
    return (
        _JETSON_CSI_HINT
        + f"Active settings: camera={args.camera!r} sensor-id={args.csi_sensor_id} "
        f"flip-method={args.csi_flip_method} {args.width}x{args.height}@{args.csi_framerate} "
        f"open-retries={args.csi_open_retries}.\n"
    )


def _usb_index_capture_backend() -> int:
    """Integer index capture: Linux uses V4L2; macOS needs AVFoundation (not V4L2)."""
    if sys.platform == "darwin":
        av = getattr(cv2, "CAP_AVFOUNDATION", None)
        if av is not None:
            return int(av)
    if sys.platform.startswith("linux"):
        return int(cv2.CAP_V4L2)
    return int(getattr(cv2, "CAP_ANY", 0))


def _usb_v4l_troubleshoot_footer(args: argparse.Namespace) -> str:
    base = (
        f"Video open failed for USB/index mode (--camera usb or a numeric index).\n"
        f"Active settings: camera={args.camera!r} usb-index={args.usb_index} "
        f"{args.width}x{args.height}.\n"
    )
    if sys.platform == "darwin":
        return base + (
            "On macOS, OpenCV uses AVFoundation (not /dev/video or V4L2).\n"
            "  • System Settings → Privacy & Security → Camera: allow Terminal, iTerm2, or VS Code.\n"
            "  • Close other apps using the camera (Zoom, Photo Booth, browser tabs).\n"
            "  • Try another index: --usb-index 1 (or 2) after: bash scripts/start_calibration.sh --usb-index 1\n"
            "  • Built-in FaceTime camera is usually index 0; external USB may be 1.\n"
            "For Jetson CSI (Argus), use --camera csi (not usb).\n"
        )
    return base + (
        "On Linux, OpenCV opens /dev/video<index> via V4L2; it is not the Jetson CSI (Argus) path.\n"
        "  • Run: ls -la /dev/video*  and  v4l2-ctl --list-devices  (needs: sudo apt-get install -y v4l-utils)\n"
        "  • If there are no /dev/video* nodes, no USB UVC camera is present—or CSI is not exposed as V4L2 on this image.\n"
        "For the built-in CSI module use: --camera csi  (not usb).\n"
    )


def _capture_troubleshoot_footer(args: argparse.Namespace) -> str:
    cam_raw = str(args.camera).strip()
    cam = cam_raw.lower()
    if cam == "csi" or "nvarguscamerasrc" in cam_raw or "!" in cam_raw:
        return _csi_troubleshoot_footer(args)
    if cam == "usb" or cam.isdigit():
        return _usb_v4l_troubleshoot_footer(args)
    return _csi_troubleshoot_footer(args)


def _camera_cli_type(value: str) -> str:
    """Reject common typos so we do not treat 'cs1' as an opaque V4L device name."""
    v = str(value).strip()
    vl = v.lower()
    if vl in ("cs1", "csl", "cis", "sci"):
        raise argparse.ArgumentTypeError(
            f"Invalid --camera {value!r}. Use 'csi' for Jetson CSI (Argus), 'usb' for /dev/video<usb-index>, "
            "or a single digit like 0 for V4L2 device index."
        )
    return v


try:
    from edge.calib.table_geometry import auto_calibration_from_corners, table_geometry_dict
    from edge.calib.table_layout import (
        break_area_polygon,
        head_string_segment_xy_m,
        kitchen_polygon,
    )

    _HAS_EDGE_AUTOCAL = True
    _HAS_TABLE_LAYOUT = True
except Exception as _e_edge:
    auto_calibration_from_corners = None
    table_geometry_dict = None
    _HAS_EDGE_AUTOCAL = False
    _HAS_TABLE_LAYOUT = False
    if __name__ == "__main__":
        print(
            f"Note: `edge` package not importable ({_e_edge!r}); using inline kitchen/foot only; "
            f"add repo root to PYTHONPATH. Current sys.path[0:3]={sys.path[:3]!r}",
            file=sys.stderr,
        )

try:
    from edge.calib.table_diagram_m import build_table_diagram_m

    _HAS_TABLE_DIAGRAM = True
except Exception as _e_dia:
    build_table_diagram_m = None  # type: ignore[assignment, misc]
    _HAS_TABLE_DIAGRAM = False
    if __name__ == "__main__":
        print(
            f"Note: table diagram overlay disabled ({_e_dia!r}).",
            file=sys.stderr,
        )


def _kitchen_foot_and_head_string_m(
    table_length_m: float, table_width_m: float
) -> tuple[
    List[Tuple[float, float]], List[Tuple[float, float]], Tuple[Tuple[float, float], Tuple[float, float]]
]:
    """Kitchen rect, foot-end quarter, and head string (break line) segment across the table."""
    l = float(table_length_m)
    w = float(table_width_m)
    if _HAS_TABLE_LAYOUT:
        k = kitchen_polygon(l, w)
        fq = break_area_polygon(l, w)
        a, b = head_string_segment_xy_m(l, w)
    else:
        hx = l * 0.25
        k = [(0.0, 0.0), (hx, 0.0), (hx, w), (0.0, w)]
        d = 0.25 * l
        fq = [(l - d, 0.0), (l, 0.0), (l, w), (l - d, w)]
        a, b = (hx, 0.0), (hx, w)
    return k, fq, (a, b)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Interactive calibration helper with a live camera, auto corners, and editing. "
            "TL/TR are the kitchen (rack) short rail; BL/BR are the opposite short rail. "
            "Points are outside cushion corners, not pocket centers."
        ),
    )
    p.add_argument(
        "--camera",
        type=_camera_cli_type,
        default="csi",
        help="Camera source: csi (Jetson Argus), usb (Linux: V4L2 /dev/video<index>; macOS: AVFoundation index), integer index, or a GStreamer pipeline string.",
    )
    p.add_argument("--usb-index", type=int, default=0)
    p.add_argument("--csi-sensor-id", type=int, default=0)
    p.add_argument("--csi-framerate", "--fps", dest="csi_framerate", type=int, default=30)
    p.add_argument("--csi-flip-method", "--flip", dest="csi_flip_method", type=int, default=0)
    p.add_argument(
        "--csi-open-retries",
        type=int,
        default=8,
        help="How many times to reopen the CSI GStreamer pipeline if open or first frame fails (Argus flakiness).",
    )
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
        "videoconvert ! video/x-raw, format=(string)BGR ! appsink drop=true max-buffers=1 sync=false"
    )


def _resolve_capture_source(
    camera: str,
    usb_index: int,
    csi_sensor_id: int,
    width: int,
    height: int,
    framerate: int,
    flip_method: int,
) -> tuple[int | str, bool]:
    cam = str(camera).strip().lower()
    use_gst = False
    source: int | str
    if cam == "csi":
        source = _csi_pipeline(
            sensor_id=int(csi_sensor_id),
            width=int(width),
            height=int(height),
            framerate=int(framerate),
            flip_method=int(flip_method),
        )
        use_gst = True
    elif cam == "usb":
        source = int(usb_index)
    elif cam.isdigit():
        source = int(cam)
    else:
        source = str(camera)
        if "!" in source or "nvarguscamerasrc" in source:
            use_gst = True
    return source, use_gst


def _capture_frame_for_source(
    camera: str,
    usb_index: int,
    csi_sensor_id: int,
    width: int,
    height: int,
    framerate: int,
    flip_method: int,
    *,
    open_retries: int = 1,
) -> np.ndarray:
    cap = _open_capture_for_source(
        camera=camera,
        usb_index=usb_index,
        csi_sensor_id=csi_sensor_id,
        width=width,
        height=height,
        framerate=framerate,
        flip_method=flip_method,
        open_retries=open_retries,
    )
    try:
        return _read_frame_from_capture(cap, camera_mode=camera)
    finally:
        cap.release()


def _open_capture_for_source(
    camera: str,
    usb_index: int,
    csi_sensor_id: int,
    width: int,
    height: int,
    framerate: int,
    flip_method: int,
    *,
    open_retries: int = 1,
) -> cv2.VideoCapture:
    source, use_gst = _resolve_capture_source(
        camera=camera,
        usb_index=usb_index,
        csi_sensor_id=csi_sensor_id,
        width=width,
        height=height,
        framerate=framerate,
        flip_method=flip_method,
    )
    attempts = max(1, int(open_retries)) if use_gst else 1
    last_err: Optional[Exception] = None
    for attempt in range(attempts):
        if use_gst:
            cap = cv2.VideoCapture(source, cv2.CAP_GSTREAMER)
        elif isinstance(source, int):
            cap = cv2.VideoCapture(source, _usb_index_capture_backend())
        else:
            cap = cv2.VideoCapture(source)
        if not use_gst and isinstance(source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
        if not use_gst:
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            last_err = RuntimeError(f"Failed to open camera source={source!r}")
        else:
            ok, probe = cap.read()
            if ok and probe is not None:
                return cap
            try:
                cap.release()
            except Exception:
                pass
            last_err = RuntimeError("Camera pipeline opened but first read() returned no frame.")
        if attempt + 1 < attempts:
            time.sleep(0.5)
    if last_err is not None:
        raise last_err
    raise RuntimeError("Camera open failed.")


def _read_frame_from_capture(cap: cv2.VideoCapture, *, camera_mode: Optional[str] = None) -> np.ndarray:
    # Drain buffered frames so redraw uses a current frame instead of stale data.
    frame: Optional[np.ndarray] = None
    grabbed = 0
    for _ in range(8):
        if not cap.grab():
            break
        grabbed += 1
    if grabbed > 0:
        ok, candidate = cap.retrieve()
        if ok and candidate is not None:
            frame = candidate
    for _ in range(2):
        ok, candidate = cap.read()
        if ok and candidate is not None:
            frame = candidate
    if frame is None:
        ok, frame = cap.read()
    if frame is None:
        msg = "Failed to capture frame from camera."
        if camera_mode is not None and str(camera_mode).strip().lower() == "csi":
            msg += "\n\n" + _JETSON_CSI_HINT
        raise RuntimeError(msg)
    return np.ascontiguousarray(frame)


def _read_preview_frame(cap: cv2.VideoCapture, *, camera_mode: Optional[str] = None) -> np.ndarray:
    """One GUI tick: decode fresh frames; copy so GStreamer/OpenCV buffer reuse cannot freeze the table view."""
    ok, a = cap.read()
    if not ok or a is None:
        msg = "Failed to capture frame from camera."
        if camera_mode is not None and str(camera_mode).strip().lower() == "csi":
            msg += "\n\n" + _JETSON_CSI_HINT
        raise RuntimeError(msg)
    ok2, b = cap.read()
    frame = b if ok2 and b is not None else a
    return np.ascontiguousarray(frame)


def _capture_frame(args: argparse.Namespace) -> np.ndarray:
    return _capture_frame_for_source(
        camera=str(args.camera),
        usb_index=int(args.usb_index),
        csi_sensor_id=int(args.csi_sensor_id),
        width=int(args.width),
        height=int(args.height),
        framerate=int(args.csi_framerate),
        flip_method=int(args.csi_flip_method),
        open_retries=int(args.csi_open_retries),
    )


def _main_screen_size_fallback() -> tuple[int, int] | None:
    """Screen pixel size for fullscreen resize (no Tk: avoids Tcl/Tk abort on some macOS versions)."""
    if sys.platform != "darwin":
        try:
            import tkinter as tk

            root = tk.Tk()
            sw, sh = int(root.winfo_screenwidth()), int(root.winfo_screenheight())
            root.destroy()
            if sw > 0 and sh > 0:
                return sw, sh
        except Exception:
            pass
        return None
    # macOS: never call tk.Tk() here — it can throw uncaught NSException in libtk (macOSVersion selector).
    try:
        out = subprocess.check_output(
            [
                "/usr/bin/osascript",
                "-e",
                'tell application "Finder" to get bounds of window of desktop',
            ],
            text=True,
            timeout=5,
        )
        raw = re.findall(r"-?\d+", out)
        if len(raw) >= 4:
            left, top, right, bottom = (int(raw[i]) for i in range(4))
            sw, sh = right - left, bottom - top
            if sw > 100 and sh > 100:
                return sw, sh
    except Exception:
        pass
    return (1920, 1080)


def _apply_fullscreen_window(win_name: str) -> None:
    """Best-effort maximize/fullscreen (macOS HighGUI often needs resize + move as fallback)."""
    sz = _main_screen_size_fallback()
    if sz is not None:
        sw, sh = sz
        try:
            cv2.resizeWindow(win_name, int(sw), int(sh))
            cv2.moveWindow(win_name, 0, 0)
        except Exception:
            pass
    try:
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    except Exception:
        pass


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
    L = float(table_length_m)
    W = float(table_width_m)
    dst = np.array(
        [
            [0.0, 0.0],
            [0.0, W],
            [L, 0.0],
            [L, W],
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


def _table_m_to_image_xy(h_image_to_table: np.ndarray, xy_m: Tuple[float, float]) -> Tuple[float, float]:
    """
    H from _estimate_homography maps homogeneous image (x,y,1) to table meters (X,Y,1); invert for table → image.
    """
    h_inv = np.linalg.inv(h_image_to_table)
    t = h_inv @ np.array([xy_m[0], xy_m[1], 1.0], dtype=np.float64)
    w = float(t[2]) + 1e-12
    return float(t[0] / w), float(t[1] / w)


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


def _line_from_points(p1: Tuple[float, float], p2: Tuple[float, float]) -> Optional[np.ndarray]:
    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])
    dx = x2 - x1
    dy = y2 - y1
    if (dx * dx + dy * dy) <= 1e-8:
        return None
    a = y1 - y2
    b = x2 - x1
    c = (x1 * y2) - (x2 * y1)
    n = float(np.hypot(a, b))
    if n <= 1e-8:
        return None
    return np.array([a / n, b / n, c / n], dtype=np.float64)


def _fit_line_from_points(points: Sequence[Tuple[float, float]]) -> Optional[np.ndarray]:
    if len(points) < 2:
        return None
    pts = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
    try:
        vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
    except cv2.error:
        return None
    # OpenCV can return 4×1 float arrays; avoid deprecated ndarray→scalar in NumPy 1.25+.
    vx_f = float(np.asarray(vx, dtype=np.float64).ravel()[0])
    vy_f = float(np.asarray(vy, dtype=np.float64).ravel()[0])
    x0_f = float(np.asarray(x0, dtype=np.float64).ravel()[0])
    y0_f = float(np.asarray(y0, dtype=np.float64).ravel()[0])
    a = vy_f
    b = -vx_f
    c = -((a * x0_f) + (b * y0_f))
    n = float(np.hypot(a, b))
    if n <= 1e-8:
        return None
    return np.array([a / n, b / n, c / n], dtype=np.float64)


def _line_intersection(line_a: np.ndarray, line_b: np.ndarray) -> Optional[Tuple[float, float]]:
    a1, b1, c1 = (float(line_a[0]), float(line_a[1]), float(line_a[2]))
    a2, b2, c2 = (float(line_b[0]), float(line_b[1]), float(line_b[2]))
    det = (a1 * b2) - (a2 * b1)
    if abs(det) <= 1e-8:
        return None
    x = ((b1 * c2) - (b2 * c1)) / det
    y = ((c1 * a2) - (c2 * a1)) / det
    return float(x), float(y)


def _clip_point_to_image(x: float, y: float, w: int, h: int) -> Tuple[float, float]:
    return (
        float(np.clip(float(x), 0.0, float(w - 1))),
        float(np.clip(float(y), 0.0, float(h - 1))),
    )


def _unit_vec2(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n <= 1e-9:
        return np.array([0.0, 0.0], dtype=np.float64)
    return (v / n).astype(np.float64)


def _cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _intersect_lines_n_d(n1: np.ndarray, d1: float, n2: np.ndarray, d2: float) -> Optional[Tuple[float, float]]:
    """Solve n1·p=d1, n2·p=d2 for p=(x,y). Lines are parallel to each other's perpendicular."""
    a = np.array([[float(n1[0]), float(n1[1])], [float(n2[0]), float(n2[1])]], dtype=np.float64)
    b = np.array([float(d1), float(d2)], dtype=np.float64)
    try:
        xy = np.linalg.solve(a, b)
    except np.linalg.LinAlgError:
        return None
    if not (np.all(np.isfinite(xy))):
        return None
    return float(xy[0]), float(xy[1])


def _pocket_throat_from_seed(
    gray: np.ndarray,
    corner: np.ndarray,
    arm1: np.ndarray,
    arm2: np.ndarray,
    w: int,
    h: int,
) -> Optional[Tuple[float, float]]:
    """
    Estimate the inner pocket throat: intersection of two lines parallel to the
    playing-surface rails (corner→arm1, corner→arm2) fit to Canny edges in the
    pocket wedge (direction away from table interior).
    """
    u = _unit_vec2(arm1 - corner)
    v = _unit_vec2(arm2 - corner)
    if float(np.linalg.norm(u)) < 1e-6 or float(np.linalg.norm(v)) < 1e-6:
        return None
    pock = _unit_vec2(-(u + v))
    if float(np.linalg.norm(pock)) < 1e-6:
        return None

    diag = float(np.hypot(float(w), float(h)))
    roi_half = int(max(36, min(0.14 * diag, 0.22 * diag)))
    ctr = corner + pock * (0.055 * diag)
    x0 = int(max(0, float(ctr[0]) - roi_half))
    x1 = int(min(w, float(ctr[0]) + roi_half))
    y0 = int(max(0, float(ctr[1]) - roi_half))
    y1 = int(min(h, float(ctr[1]) + roi_half))
    if x1 - x0 < 24 or y1 - y0 < 24:
        return None

    patch = gray[y0:y1, x0:x1]
    blur = cv2.GaussianBlur(patch, (5, 5), 0)
    med = float(np.median(blur))
    lo = int(max(12.0, 0.52 * med))
    hi = int(min(248.0, max(lo + 8.0, 1.38 * med)))
    edges = cv2.Canny(blur, lo, hi)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    tol_strip = max(6.0, 0.015 * diag)
    max_along = 0.42 * diag
    min_pock = 3.0

    n_u = _unit_vec2(np.array([-u[1], u[0]], dtype=np.float64))
    n_v = _unit_vec2(np.array([-v[1], v[0]], dtype=np.float64))

    def collect_d_values(dir_rail: np.ndarray, normal: np.ndarray) -> List[float]:
        ds: List[float] = []
        ys, xs = np.where(edges > 0)
        for yi, xi in zip(ys.tolist(), xs.tolist()):
            px = float(x0 + int(xi))
            py = float(y0 + int(yi))
            p = np.array([px, py], dtype=np.float64)
            if float(np.dot(p - corner, pock)) < min_pock:
                continue
            perp = abs(_cross2(p - corner, dir_rail)) / (float(np.linalg.norm(dir_rail)) + 1e-9)
            if perp > tol_strip:
                continue
            along = float(np.dot(p - corner, -dir_rail))
            if along < 4.0 or along > max_along:
                continue
            ds.append(float(normal[0] * px + normal[1] * py))
        return ds

    du = collect_d_values(u, n_u)
    dv = collect_d_values(v, n_v)
    if len(du) < 6 or len(dv) < 6:
        return None

    du_arr = np.array(du, dtype=np.float64)
    dv_arr = np.array(dv, dtype=np.float64)

    def _try_pair(pu: float, pv: float) -> Optional[Tuple[float, float]]:
        inter_l = _intersect_lines_n_d(n_u, pu, n_v, pv)
        if inter_l is None:
            return None
        ix_l, iy_l = inter_l
        dm = float(np.hypot(ix_l - float(corner[0]), iy_l - float(corner[1])))
        if dm > 0.30 * diag or dm < 0.002 * diag:
            return None
        return _clip_point_to_image(ix_l, iy_l, w, h)

    d_u_m = float(np.median(du_arr))
    d_v_m = float(np.median(dv_arr))
    cand = _try_pair(d_u_m, d_v_m)
    if cand is not None:
        return cand
    # Second pass: percentiles favor inner jaw when median sits between two parallel rails.
    for pu, pv in (
        (float(np.percentile(du_arr, 30)), float(np.percentile(dv_arr, 30))),
        (float(np.percentile(du_arr, 70)), float(np.percentile(dv_arr, 70))),
    ):
        cand = _try_pair(pu, pv)
        if cand is not None:
            return cand
    return None


def _refine_quad_to_pocket_throats(
    gray: np.ndarray,
    physical_tl_tr_bl_br: Sequence[Tuple[float, float]],
    w: int,
    h: int,
) -> Optional[List[Tuple[float, float]]]:
    """Return four throat points (physical TL,TR,BL,BR order) if all corners refine."""
    tl = np.array(physical_tl_tr_bl_br[0], dtype=np.float64)
    tr = np.array(physical_tl_tr_bl_br[1], dtype=np.float64)
    bl = np.array(physical_tl_tr_bl_br[2], dtype=np.float64)
    br = np.array(physical_tl_tr_bl_br[3], dtype=np.float64)
    seeds = [
        (tl, tr, bl),
        (tr, tl, br),
        (bl, tl, br),
        (br, tr, bl),
    ]
    out: List[Tuple[float, float]] = []
    for corner, a1, a2 in seeds:
        t = _pocket_throat_from_seed(gray, corner, a1, a2, w, h)
        if t is None:
            return None
        out.append(t)
    return out


def _quad_area_xy(pts: Sequence[Tuple[float, float]]) -> float:
    arr = np.array(pts, dtype=np.float32).reshape(-1, 1, 2)
    return abs(float(cv2.contourArea(arr)))


def _quad_min_corner_inset(quad: np.ndarray, w: int, h: int) -> float:
    """Smallest distance from any vertex to the image border (detects frame-filling quads)."""
    m = float("inf")
    for row in quad.reshape(-1, 2):
        x, y = float(row[0]), float(row[1])
        m = min(m, x, y, float(w - 1) - x, float(h - 1) - y)
    return float(m)


def _refine_quad_with_hough(gray: np.ndarray, seed_quad: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    h, w = gray.shape[:2]
    if len(seed_quad) != 4:
        return [(float(x), float(y)) for x, y in seed_quad]
    ordered_seed = _order_points_tl_tr_bl_br([(float(x), float(y)) for x, y in seed_quad])
    tl = np.array(ordered_seed[0], dtype=np.float64)
    tr = np.array(ordered_seed[1], dtype=np.float64)
    bl = np.array(ordered_seed[2], dtype=np.float64)
    br = np.array(ordered_seed[3], dtype=np.float64)
    side_pairs = [(tl, tr), (tr, br), (bl, br), (tl, bl)]  # top, right, bottom, left
    side_dirs: List[np.ndarray] = []
    side_lines: List[np.ndarray] = []
    for a, b in side_pairs:
        line = _line_from_points((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
        if line is None:
            return ordered_seed
        side_lines.append(line)
        v = b - a
        n = float(np.linalg.norm(v))
        if n <= 1e-8:
            return ordered_seed
        side_dirs.append(v / n)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    med = float(np.median(blur))
    lo = int(max(18.0, 0.60 * med))
    hi = int(min(240.0, max(lo + 10.0, 1.35 * med)))
    edges = cv2.Canny(blur, lo, hi)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    min_line_length = max(36, int(0.14 * min(h, w)))
    lines_p = cv2.HoughLinesP(
        edges,
        1.0,
        np.pi / 180.0,
        threshold=max(40, int(0.08 * min(h, w))),
        minLineLength=min_line_length,
        maxLineGap=22,
    )
    if lines_p is None:
        return ordered_seed

    side_points: List[List[Tuple[float, float]]] = [[], [], [], []]
    dist_band = max(22.0, 0.12 * float(min(h, w)))
    align_threshold = float(np.cos(np.deg2rad(24.0)))

    for seg in lines_p.reshape(-1, 4):
        p1 = np.array([float(seg[0]), float(seg[1])], dtype=np.float64)
        p2 = np.array([float(seg[2]), float(seg[3])], dtype=np.float64)
        seg_v = p2 - p1
        seg_len = float(np.linalg.norm(seg_v))
        if seg_len < float(min_line_length):
            continue
        seg_dir = seg_v / seg_len
        mid = 0.5 * (p1 + p2)

        best_side_idx = -1
        best_score = -1e9
        for side_idx in range(4):
            align = abs(float(np.dot(seg_dir, side_dirs[side_idx])))
            if align < align_threshold:
                continue
            distance = abs(
                float(
                    (side_lines[side_idx][0] * mid[0])
                    + (side_lines[side_idx][1] * mid[1])
                    + side_lines[side_idx][2]
                )
            )
            if distance > dist_band:
                continue
            score = (1.8 * align) + (0.8 * (seg_len / float(min(h, w)))) - (distance / dist_band)
            if score > best_score:
                best_score = score
                best_side_idx = side_idx
        if best_side_idx >= 0:
            side_points[best_side_idx].append((float(p1[0]), float(p1[1])))
            side_points[best_side_idx].append((float(p2[0]), float(p2[1])))

    refined_lines: List[np.ndarray] = []
    for side_idx in range(4):
        if len(side_points[side_idx]) >= 6:
            fitted = _fit_line_from_points(side_points[side_idx])
            refined_lines.append(fitted if fitted is not None else side_lines[side_idx])
        else:
            refined_lines.append(side_lines[side_idx])

    tl_i = _line_intersection(refined_lines[0], refined_lines[3])
    tr_i = _line_intersection(refined_lines[0], refined_lines[1])
    bl_i = _line_intersection(refined_lines[2], refined_lines[3])
    br_i = _line_intersection(refined_lines[2], refined_lines[1])
    if not (tl_i and tr_i and bl_i and br_i):
        return ordered_seed

    refined_quad = [
        _clip_point_to_image(float(tl_i[0]), float(tl_i[1]), w, h),
        _clip_point_to_image(float(tr_i[0]), float(tr_i[1]), w, h),
        _clip_point_to_image(float(bl_i[0]), float(bl_i[1]), w, h),
        _clip_point_to_image(float(br_i[0]), float(br_i[1]), w, h),
    ]
    refined_ordered = _order_points_tl_tr_bl_br(refined_quad)
    refined_area = abs(float(cv2.contourArea(np.array(refined_ordered, dtype=np.float32))))
    seed_area = abs(float(cv2.contourArea(np.array(ordered_seed, dtype=np.float32))))
    if refined_area < max(0.05 * float(w * h), 0.35 * seed_area):
        return ordered_seed
    return refined_ordered


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
    gray_eq = cv2.equalizeHist(gray)
    blur = cv2.GaussianBlur(gray_eq, (5, 5), 0)
    med = float(np.median(blur))
    lo = int(max(18.0, 0.60 * med))
    hi = int(min(240.0, max(lo + 10.0, 1.35 * med)))
    edges = cv2.Canny(blur, lo, hi)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _default_corners(h, w)

    wh = float(w * h)
    min_contour_area = 0.08 * wh
    # Prefer the playfield-sized quad, not the largest hull (often the whole room / frame).
    max_quad_area = 0.70 * wh
    min_quad_area = 0.055 * wh
    inset_target = 0.035 * float(min(h, w))

    scored: List[Tuple[float, np.ndarray]] = []
    fallback: List[Tuple[float, np.ndarray]] = []

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:24]:
        area = float(cv2.contourArea(contour))
        if area < min_contour_area:
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
        inset = _quad_min_corner_inset(snapped, w, h)
        fallback.append((snapped_area, snapped.copy()))
        if min_quad_area <= snapped_area <= max_quad_area:
            inset_w = min(1.0, max(0.15, inset / max(inset_target, 1.0)))
            scored.append((snapped_area * inset_w, snapped.copy()))

        eps = 0.012 * cv2.arcLength(hull.astype(np.float32), True)
        approx = cv2.approxPolyDP(hull.astype(np.float32), eps, True).reshape(-1, 2).astype(np.float64)
        if approx.shape[0] == 4:
            approx_ordered = np.array(_order_points_tl_tr_bl_br(approx.tolist()), dtype=np.float64)
            approx_area = abs(float(cv2.contourArea(approx_ordered.astype(np.float32))))
            inset = _quad_min_corner_inset(approx_ordered, w, h)
            fallback.append((approx_area, approx_ordered.copy()))
            if min_quad_area <= approx_area <= max_quad_area:
                inset_w = min(1.0, max(0.15, inset / max(inset_target, 1.0)))
                scored.append((approx_area * inset_w, approx_ordered.copy()))

    best_quad: Optional[np.ndarray] = None
    best_quad_area = -1.0
    if scored:
        _, best_quad = max(scored, key=lambda t: t[0])
        best_quad_area = float(_quad_area_xy([(float(x), float(y)) for x, y in best_quad.reshape(-1, 2)]))
    else:
        capped = [(qa, q) for qa, q in fallback if qa <= max_quad_area and qa >= min_quad_area * 0.55]
        if capped:
            best_quad_area, best_quad = max(capped, key=lambda t: t[0])
        else:
            loose = [(qa, q) for qa, q in fallback if qa <= 0.82 * wh]
            if loose:
                best_quad_area, best_quad = max(loose, key=lambda t: t[0])
            elif fallback:
                best_quad_area, best_quad = max(fallback, key=lambda t: t[0])
            else:
                best_quad = None

    if best_quad is None or best_quad_area <= 1.0:
        return _default_corners(h, w)

    hough_refined = _refine_quad_with_hough(gray, best_quad.tolist())
    phys_hough = _order_physical_table_corners(_order_points_tl_tr_bl_br(hough_refined))
    throat_pts = _refine_quad_to_pocket_throats(gray, phys_hough, w, h)
    if throat_pts is not None:
        ta = _quad_area_xy(throat_pts)
        ha = max(_quad_area_xy(hough_refined), 1.0)
        if (
            ta >= 0.09 * float(w * h)
            and ta <= min(0.62 * float(w * h), 1.5 * max(ha, 0.55 * float(best_quad_area)))
        ):
            return _order_physical_table_corners(throat_pts)

    refined = _refine_corner_seeds(gray, hough_refined)
    refined_ordered = _order_points_tl_tr_bl_br(refined)
    refined_area = abs(float(cv2.contourArea(np.array(refined_ordered, dtype=np.float32))))
    hough_area = abs(float(cv2.contourArea(np.array(hough_refined, dtype=np.float32))))
    if refined_area < 0.4 * best_quad_area:
        if hough_area >= 0.4 * best_quad_area:
            return _order_physical_table_corners(hough_refined)
        return _order_physical_table_corners([(float(x), float(y)) for x, y in best_quad])
    return _order_physical_table_corners(refined_ordered)


def _refine_side_pocket_seed(
    gray: np.ndarray,
    seed_xy: Tuple[float, float],
    rail_vec: np.ndarray,
) -> Tuple[float, float]:
    h, w = gray.shape[:2]
    seed = np.array([float(seed_xy[0]), float(seed_xy[1])], dtype=np.float64)
    rail_len = float(np.linalg.norm(rail_vec))
    if rail_len <= 1e-6:
        return _clip_point_to_image(float(seed[0]), float(seed[1]), w, h)

    rail_u = rail_vec.astype(np.float64) / rail_len
    rail_n = np.array([-rail_u[1], rail_u[0]], dtype=np.float64)

    search_radius = int(max(24.0, min(0.30 * rail_len, 0.24 * float(min(h, w)))))
    x0 = max(0, int(round(seed[0])) - search_radius)
    x1 = min(w, int(round(seed[0])) + search_radius + 1)
    y0 = max(0, int(round(seed[1])) - search_radius)
    y1 = min(h, int(round(seed[1])) + search_radius + 1)
    if x1 <= x0 or y1 <= y0:
        return _clip_point_to_image(float(seed[0]), float(seed[1]), w, h)

    patch = gray[y0:y1, x0:x1]
    if patch.size == 0:
        return _clip_point_to_image(float(seed[0]), float(seed[1]), w, h)

    patch_blur = cv2.GaussianBlur(patch, (5, 5), 0)
    patch_h, patch_w = patch_blur.shape[:2]
    seed_local = np.array([seed[0] - float(x0), seed[1] - float(y0)], dtype=np.float64)
    seed_local[0] = float(np.clip(seed_local[0], 0.0, float(max(0, patch_w - 1))))
    seed_local[1] = float(np.clip(seed_local[1], 0.0, float(max(0, patch_h - 1))))

    dark_thresh = float(np.percentile(patch_blur, 22))
    dark_mask = (patch_blur <= dark_thresh).astype(np.uint8) * 255

    bh_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    blackhat = cv2.morphologyEx(patch_blur, cv2.MORPH_BLACKHAT, bh_kernel)
    bh_thresh = float(np.percentile(blackhat, 78))
    bh_mask = (blackhat >= bh_thresh).astype(np.uint8) * 255

    pocket_mask = cv2.bitwise_and(dark_mask, bh_mask)
    if int(np.count_nonzero(pocket_mask)) < 20:
        pocket_mask = cv2.bitwise_or(dark_mask, bh_mask)
    if int(np.count_nonzero(pocket_mask)) < 20:
        pocket_mask = dark_mask

    inv = cv2.GaussianBlur(255 - patch_blur, (5, 5), 0)
    try:
        circles = cv2.HoughCircles(
            inv,
            cv2.HOUGH_GRADIENT,
            dp=1.15,
            minDist=max(10, search_radius // 4),
            param1=64,
            param2=10,
            minRadius=max(4, search_radius // 12),
            maxRadius=max(12, search_radius // 2),
        )
    except cv2.error:
        circles = None
    if circles is not None and len(circles[0]) > 0:
        best_c = None
        best_cs = -1e9
        for cx_c, cy_c, _r in circles[0]:
            xi = int(np.clip(round(cx_c), 0, patch_w - 1))
            yi = int(np.clip(round(cy_c), 0, patch_h - 1))
            local_dark = 1.0 - (float(patch_blur[yi, xi]) / 255.0)
            dloc = np.array([cx_c, cy_c], dtype=np.float64) - seed_local
            sigma2 = float(max(64.0, (0.35 * float(search_radius)) ** 2))
            dpen = float(np.exp(-float(np.dot(dloc, dloc)) / (2.0 * sigma2)))
            sc = 3.5 * local_dark + 0.9 * dpen
            if sc > best_cs:
                best_cs = sc
                best_c = (cx_c, cy_c)
        if best_c is not None and best_cs > 1.1:
            cx = float(best_c[0]) + float(x0)
            cy = float(best_c[1]) + float(y0)
            delta = np.array([cx - seed[0], cy - seed[1]], dtype=np.float64)
            along = float(np.clip(np.dot(delta, rail_u), -0.22 * rail_len, 0.22 * rail_len))
            across = float(np.clip(np.dot(delta, rail_n), -0.14 * rail_len, 0.14 * rail_len))
            refined = seed + (along * rail_u) + (across * rail_n)
            return _clip_point_to_image(float(refined[0]), float(refined[1]), w, h)

    pocket_mask = cv2.morphologyEx(pocket_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    pocket_mask = cv2.morphologyEx(pocket_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(pocket_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_score = -float('inf')
    best_local_xy: Optional[np.ndarray] = None
    patch_area = float(max(1, patch_h * patch_w))
    patch_diag = float(max(1.0, np.hypot(patch_w, patch_h)))

    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 24.0:
            continue
        m = cv2.moments(contour)
        if float(m['m00']) <= 1e-6:
            continue

        cx = float(m['m10'] / m['m00'])
        cy = float(m['m01'] / m['m00'])
        x_b, y_b, w_b, h_b = cv2.boundingRect(contour)
        aspect = float(w_b) / float(max(1, h_b))
        if not (0.22 <= aspect <= 4.5):
            continue

        peri = float(cv2.arcLength(contour, True))
        circularity = 0.0 if peri <= 1e-6 else float((4.0 * np.pi * area) / (peri * peri))

        contour_mask = np.zeros((patch_h, patch_w), dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, thickness=-1)
        mean_intensity = float(cv2.mean(patch_blur, mask=contour_mask)[0])
        darkness = 1.0 - (mean_intensity / 255.0)

        delta_local = np.array([cx, cy], dtype=np.float64) - seed_local
        dist_seed = float(np.linalg.norm(delta_local)) / patch_diag
        dist_along = abs(float(np.dot(delta_local, rail_u))) / float(max(1.0, search_radius))
        dist_across = abs(float(np.dot(delta_local, rail_n))) / float(max(1.0, search_radius))

        area_term = min(1.0, area / (0.12 * patch_area))
        shape_term = max(0.0, 1.0 - abs(circularity - 0.78))
        score = (
            (3.2 * darkness)
            + (1.1 * area_term)
            + (0.65 * shape_term)
            - (1.2 * dist_seed)
            - (1.6 * dist_across)
            - (0.4 * dist_along)
        )
        if score > best_score:
            best_score = score
            best_local_xy = np.array([cx, cy], dtype=np.float64)

    if best_local_xy is None or best_score < 0.88:
        mask = dark_mask > 0
        if int(np.count_nonzero(mask)) < 24:
            return _clip_point_to_image(float(seed[0]), float(seed[1]), w, h)

        ys, xs = np.where(mask)
        px = patch_blur[ys, xs].astype(np.float64)
        delta_x = xs.astype(np.float64) - float(seed_local[0])
        delta_y = ys.astype(np.float64) - float(seed_local[1])
        dist2 = (delta_x * delta_x) + (delta_y * delta_y)
        sigma2 = float(max(16.0, (0.38 * float(search_radius)) ** 2))
        distance_weight = np.exp(-dist2 / (2.0 * sigma2))
        weights = ((dark_thresh - px) + 1.0) * distance_weight
        cx = float(np.average(xs.astype(np.float64), weights=weights))
        cy = float(np.average(ys.astype(np.float64), weights=weights))
        best_local_xy = np.array([cx, cy], dtype=np.float64)

    cx = float(best_local_xy[0]) + float(x0)
    cy = float(best_local_xy[1]) + float(y0)
    delta = np.array([cx - seed[0], cy - seed[1]], dtype=np.float64)
    along = float(np.clip(np.dot(delta, rail_u), -0.22 * rail_len, 0.22 * rail_len))
    across = float(np.clip(np.dot(delta, rail_n), -0.14 * rail_len, 0.14 * rail_len))
    refined = seed + (along * rail_u) + (across * rail_n)
    return _clip_point_to_image(float(refined[0]), float(refined[1]), w, h)


def _estimate_side_pockets_from_corners(
    frame: np.ndarray,
    corners: Sequence[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    if len(corners) != 4:
        return []

    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    tl, tr, bl, br = [np.array(p, dtype=np.float64) for p in corners]

    # Side pockets sit on the two long rails (TL–BL and TR–BR), centered on each rail line.
    left_mid = 0.5 * (tl + bl)
    right_mid = 0.5 * (tr + br)
    left_seed = _refine_side_pocket_seed(gray, (float(left_mid[0]), float(left_mid[1])), bl - tl)
    right_seed = _refine_side_pocket_seed(gray, (float(right_mid[0]), float(right_mid[1])), br - tr)

    left_seed = _clip_point_to_image(float(left_seed[0]), float(left_seed[1]), w, h)
    right_seed = _clip_point_to_image(float(right_seed[0]), float(right_seed[1]), w, h)
    return _normalize_side_pockets_to_rails([left_seed, right_seed], corners, frame.shape[:2])


def _distance_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx = float(bx - ax)
    aby = float(by - ay)
    apx = float(px - ax)
    apy = float(py - ay)
    denom = float((abx * abx) + (aby * aby))
    if denom <= 1e-9:
        return float(np.hypot(apx, apy))
    t = float(np.clip(((apx * abx) + (apy * aby)) / denom, 0.0, 1.0))
    qx = float(ax + (t * abx))
    qy = float(ay + (t * aby))
    return float(np.hypot(px - qx, py - qy))


def _normalize_side_pockets_to_rails(
    side_points: Sequence[Tuple[float, float]],
    corners: Sequence[Tuple[float, float]],
    shape_hw: Tuple[int, int],
) -> List[Tuple[float, float]]:
    if len(side_points) != 2 or len(corners) != 4:
        return list(side_points)
    h, w = int(shape_hw[0]), int(shape_hw[1])
    tl, tr, bl, br = [np.array(p, dtype=np.float64) for p in corners]
    left_mid = 0.5 * (tl + bl)
    right_mid = 0.5 * (tr + br)

    def _cost(point_xy: Tuple[float, float], rail_a: np.ndarray, rail_b: np.ndarray, rail_mid: np.ndarray) -> float:
        px, py = float(point_xy[0]), float(point_xy[1])
        d_rail = _distance_point_to_segment(px, py, float(rail_a[0]), float(rail_a[1]), float(rail_b[0]), float(rail_b[1]))
        d_mid = float(np.hypot(px - float(rail_mid[0]), py - float(rail_mid[1])))
        return d_rail + (0.35 * d_mid)

    p0 = (float(side_points[0][0]), float(side_points[0][1]))
    p1 = (float(side_points[1][0]), float(side_points[1][1]))

    cost_keep = _cost(p0, tl, bl, left_mid) + _cost(p1, tr, br, right_mid)
    cost_swap = _cost(p1, tl, bl, left_mid) + _cost(p0, tr, br, right_mid)

    if cost_swap < cost_keep:
        left_pt, right_pt = p1, p0
    else:
        left_pt, right_pt = p0, p1

    left_xy = _project_point_to_segment(left_pt, tl, bl)
    right_xy = _project_point_to_segment(right_pt, tr, br)
    left_xy = _clip_point_to_image(float(left_xy[0]), float(left_xy[1]), w, h)
    right_xy = _clip_point_to_image(float(right_xy[0]), float(right_xy[1]), w, h)
    return [left_xy, right_xy]


def _project_t_on_segment(point_xy: Tuple[float, float], seg_a: np.ndarray, seg_b: np.ndarray) -> float:
    p = np.array([float(point_xy[0]), float(point_xy[1])], dtype=np.float64)
    a = seg_a.astype(np.float64)
    b = seg_b.astype(np.float64)
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom <= 1e-9:
        return 0.5
    t = float(np.dot(p - a, ab) / denom)
    return float(np.clip(t, 0.0, 1.0))


def _project_point_to_segment(point_xy: Tuple[float, float], seg_a: np.ndarray, seg_b: np.ndarray) -> Tuple[float, float]:
    t = _project_t_on_segment(point_xy, seg_a, seg_b)
    p = seg_a.astype(np.float64) + (t * (seg_b.astype(np.float64) - seg_a.astype(np.float64)))
    return float(p[0]), float(p[1])


def _remap_side_pockets_between_corners(
    frame: np.ndarray,
    old_side_points: Sequence[Tuple[float, float]],
    old_corners: Sequence[Tuple[float, float]],
    new_corners: Sequence[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    if len(old_side_points) != 2 or len(old_corners) != 4 or len(new_corners) != 4:
        return _estimate_side_pockets_from_corners(frame, new_corners)
    old_tl, old_tr, old_bl, old_br = [np.array(p, dtype=np.float64) for p in old_corners]
    new_tl, new_tr, new_bl, new_br = [np.array(p, dtype=np.float64) for p in new_corners]

    old_norm = _normalize_side_pockets_to_rails(old_side_points, old_corners, frame.shape[:2])
    t_ls = _project_t_on_segment(old_norm[0], old_tl, old_bl)
    t_rs = _project_t_on_segment(old_norm[1], old_tr, old_br)

    seed_left = new_tl + (t_ls * (new_bl - new_tl))
    seed_right = new_tr + (t_rs * (new_br - new_tr))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    left_refined = _refine_side_pocket_seed(gray, (float(seed_left[0]), float(seed_left[1])), new_bl - new_tl)
    right_refined = _refine_side_pocket_seed(gray, (float(seed_right[0]), float(seed_right[1])), new_br - new_tr)
    return _normalize_side_pockets_to_rails([left_refined, right_refined], new_corners, frame.shape[:2])

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


def _order_physical_table_corners_impl(
    points: List[Tuple[float, float]],
    *,
    head_toward_small_image_y: bool,
) -> List[Tuple[float, float]]:
    """
    Order four corners as physical TL, TR, BL, BR given which short-rail end is "head".

    head_toward_small_image_y: if True, the head short rail is the one whose midpoint
    has smaller image Y; if False, the head rail is the one with larger image Y.
    """
    pts = np.array(points, dtype=np.float64)
    if pts.shape[0] != 4:
        raise ValueError("Need exactly 4 corners.")
    c = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    order = np.argsort(angles)
    p = pts[order]
    p0, p1, p2, p3 = p[0], p[1], p[2], p[3]

    def dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    len01 = dist(p0, p1)
    len12 = dist(p1, p2)
    len23 = dist(p2, p3)
    len30 = dist(p3, p0)
    sum_a = len01 + len23
    sum_b = len12 + len30

    def mid(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return 0.5 * (a + b)

    def head_is_first_short_pair(p_a: np.ndarray, p_b: np.ndarray, p_c: np.ndarray, p_d: np.ndarray) -> bool:
        m01 = float(mid(p_a, p_b)[1])
        m23 = float(mid(p_c, p_d)[1])
        return (m01 <= m23) if head_toward_small_image_y else (m01 >= m23)

    if sum_a <= sum_b:
        if head_is_first_short_pair(p0, p1, p2, p3):
            head_a, head_b = p0, p1
            foot_a, foot_b = p2, p3
        else:
            head_a, head_b = p2, p3
            foot_a, foot_b = p0, p1
    else:
        if head_is_first_short_pair(p1, p2, p3, p0):
            head_a, head_b = p1, p2
            foot_a, foot_b = p3, p0
        else:
            head_a, head_b = p3, p0
            foot_a, foot_b = p1, p2

    if float(head_a[0]) <= float(head_b[0]):
        tl, tr = head_a, head_b
    else:
        tl, tr = head_b, head_a
    if float(foot_a[0]) <= float(foot_b[0]):
        bl, br = foot_a, foot_b
    else:
        bl, br = foot_b, foot_a
    return [
        (float(tl[0]), float(tl[1])),
        (float(tr[0]), float(tr[1])),
        (float(bl[0]), float(bl[1])),
        (float(br[0]), float(br[1])),
    ]


def _order_physical_table_corners(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Order four detected corners as physical TL, TR, BL, BR.

    TL and TR share the head short rail (kitchen / rack). BL and BR share the foot short rail.
    Head vs foot along image Y is ambiguous (camera can show kitchen at top or bottom); we try
    both and keep the labeling closest to image-axis TL/TR/BL/BR from the same four points.
    """
    if len(points) != 4:
        raise ValueError("Need exactly 4 corners.")
    flat = [(float(x), float(y)) for x, y in points]
    img_ref = _order_points_tl_tr_bl_br(flat)
    phys_lo = _order_physical_table_corners_impl(flat, head_toward_small_image_y=True)
    phys_hi = _order_physical_table_corners_impl(flat, head_toward_small_image_y=False)

    def _match_cost(phys: List[Tuple[float, float]]) -> float:
        return float(
            sum(
                (phys[i][0] - img_ref[i][0]) ** 2 + (phys[i][1] - img_ref[i][1]) ** 2
                for i in range(4)
            )
        )

    return phys_lo if _match_cost(phys_lo) <= _match_cost(phys_hi) else phys_hi


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
        ls_m = (0.5 * table_length_m, 0.0)
        rs_m = (0.5 * table_length_m, table_width_m)
    L = float(table_length_m)
    W = float(table_width_m)
    k_m, foot_m, _ = _kitchen_foot_and_head_string_m(L, W)
    return {
        "H": [[float(v) for v in row] for row in h.tolist()],
        "pockets": [
            {"label": "top_left_corner", "center_xy_m": [0.0, 0.0], "radius_m": pocket_radius_m},
            {"label": "top_right_corner", "center_xy_m": [0.0, W], "radius_m": pocket_radius_m},
            {"label": "bottom_left_corner", "center_xy_m": [L, 0.0], "radius_m": pocket_radius_m},
            {"label": "bottom_right_corner", "center_xy_m": [L, W], "radius_m": pocket_radius_m},
            {"label": "left_side_pocket", "center_xy_m": [ls_m[0], ls_m[1]], "radius_m": pocket_radius_m},
            {"label": "right_side_pocket", "center_xy_m": [rs_m[0], rs_m[1]], "radius_m": pocket_radius_m},
        ],
        "table_length_m": table_length_m,
        "table_width_m": table_width_m,
        "kitchen_polygon_xy_m": [[float(x), float(y)] for x, y in k_m],
        "break_area_polygon_xy_m": [[float(x), float(y)] for x, y in foot_m],
    }


def main() -> None:
    args = _parse_args()
    out_path = Path(str(args.out)).expanduser()
    detected_default_table_size = _detected_default_table_size(out_path)
    selected_table_size = _detected_default_table_size(out_path)
    selected_units = str(args.units)
    live_capture: Optional[cv2.VideoCapture] = None
    # Backward compatibility for direct invocation snippets on Orin Nano:
    # newer script expects --csi-flip-method, older snippets may pass --flip.
    # argparse already aliases --flip, so nothing else is needed besides keeping
    # this code path explicit and stable.
    try:
        live_capture = _open_capture_for_source(
            camera=str(args.camera),
            usb_index=int(args.usb_index),
            csi_sensor_id=int(args.csi_sensor_id),
            width=int(args.width),
            height=int(args.height),
            framerate=int(args.csi_framerate),
            flip_method=int(args.csi_flip_method),
            open_retries=int(args.csi_open_retries),
        )
        img = _read_frame_from_capture(live_capture, camera_mode=str(args.camera))
    except Exception as exc:
        raise RuntimeError(f"{exc}\n\n{_capture_troubleshoot_footer(args)}") from exc

    win = "calib-click"
    try:
        corner_points: List[Tuple[float, float]] = _estimate_outside_corners(img)
    except Exception as exc:
        h, w = img.shape[:2]
        corner_points = _default_corners(h, w)
        print(f"AUTO corner detect failed ({exc}); using fallback corners.", file=sys.stderr)
    print("Auto corners (TL,TR,BL,BR):", json.dumps(corner_points))
    active_point_idx: Optional[int] = None
    dragging = False
    view = img.copy()

    h_img, w_img = img.shape[:2]
    flip_view_h = False
    flip_view_v = False
    view_step_mode = "fine"
    row_spacing = 34
    radio_radius = 8
    radio_hit_radius = 14

    menu_margin = 12
    menu_padding = 16
    menu_gap = 18
    table_title_gap = 20
    units_title_gap = 18
    view_title_gap = 20
    col_gap = 20
    col1_width_frac = 0.38
    estimated_menu_w = 780
    panel_drag_handle_h = 44
    # Initial height budget for ui_scale only; refined after _view_control_layout exists.
    estimated_menu_h = 540
    safe_w = max(240, w_img - 2 * menu_margin)
    safe_h = max(240, h_img - 2 * menu_margin)
    ui_scale = min(1.0, float(safe_w) / float(estimated_menu_w), float(safe_h) / float(estimated_menu_h))
    if ui_scale < 1.0:
        row_spacing = max(18, int(round(row_spacing * ui_scale)))
        menu_padding = max(8, int(round(menu_padding * ui_scale)))
        menu_gap = max(8, int(round(menu_gap * ui_scale)))
        table_title_gap = max(12, int(round(table_title_gap * ui_scale)))
        units_title_gap = max(12, int(round(units_title_gap * ui_scale)))
        view_title_gap = max(12, int(round(view_title_gap * ui_scale)))
        col_gap = max(10, int(round(col_gap * ui_scale)))
        radio_radius = max(6, int(round(radio_radius * ui_scale)))
        radio_hit_radius = max(10, int(round(radio_hit_radius * ui_scale)))
        estimated_menu_w = max(420, int(round(estimated_menu_w * ui_scale)))
        panel_drag_handle_h = max(34, int(round(panel_drag_handle_h * ui_scale)))
    else:
        panel_drag_handle_h = max(34, panel_drag_handle_h)

    def _view_control_layout(view_left: int, view_top: int) -> Dict[str, Any]:
        """Vertical stack with reserved label bands (no overlap) and a symmetric pan cross."""
        button_w = max(34, int(round(40 * ui_scale)))
        button_h = max(26, int(round(28 * ui_scale)))
        v_step = int(max(34, round(row_spacing * 1.05)))
        rot_btn_w = max(68, button_w + 30)
        rot90_w = max(58, int(round(62 * ui_scale)))
        lab = int(14 * max(1.0, ui_scale))
        blk = int(12 * max(1.0, ui_scale))

        y = int(view_top)
        orient_label_y = y + 2
        y += lab + 8
        flip_h_center = (view_left, y)
        y += v_step
        flip_v_center = (view_left, y)
        y += v_step + blk

        scale_label_y = y + 2
        y += lab + 8
        zy = y
        zoom_minus_rect = (view_left, zy, view_left + button_w, zy + button_h)
        zoom_plus_rect = (view_left + button_w + 10, zy, view_left + 2 * button_w + 10, zy + button_h)
        y = zy + button_h + int(20 * max(1.0, ui_scale))

        pan_label_y = y + 2
        y += lab + 8
        s = max(28, int(round(32 * ui_scale)))
        g = max(8, int(round(10 * ui_scale)))
        cx = view_left + s + g + s // 2
        y0 = y
        pan_up_rect = (cx - s // 2, y0, cx + s // 2, y0 + s)
        y1 = y0 + s + g
        pan_left_rect = (cx - s - g, y1, cx - g, y1 + s)
        pan_right_rect = (cx + g, y1, cx + g + s, y1 + s)
        y2 = y1 + s + g
        pan_down_rect = (cx - s // 2, y2, cx + s // 2, y2 + s)
        y = y2 + s + int(22 * max(1.0, ui_scale))

        rotate_label_y = y + 2
        y += lab + 8
        rot_minus_rect = (view_left, y, view_left + rot_btn_w, y + button_h)
        rot_plus_rect = (
            view_left + rot_btn_w + 10,
            y,
            view_left + 2 * rot_btn_w + 10,
            y + button_h,
        )
        y += button_h + int(14 * max(1.0, ui_scale))
        rotate_90_ccw_rect = (view_left, y, view_left + rot90_w, y + button_h)
        rotate_90_cw_rect = (
            view_left + rot90_w + 10,
            y,
            view_left + 2 * rot90_w + 10,
            y + button_h,
        )
        tilt_hint_y = y + button_h + int(10 * max(1.0, ui_scale))
        y = tilt_hint_y + int(22 * max(1.0, ui_scale))

        nudge_label_y = y + 2
        y += lab + 8
        step_subtitle_y = y + 2
        y += int(16 * max(1.0, ui_scale))
        step_row_y = y
        step_fine_center = (view_left, step_row_y)
        step_coarse_center = (view_left + int(140 * max(1.0, ui_scale)), step_row_y)
        step_hint_y = step_row_y + v_step + int(16 * max(1.0, ui_scale))
        y = step_hint_y + int(22 * max(1.0, ui_scale))
        reset_w = max(158, int(168 * max(1.0, ui_scale)))
        reset_h = max(28, int(30 * max(1.0, ui_scale)))
        reset_rect = (view_left, y, view_left + reset_w, y + reset_h)
        return {
            "orient_label_y": orient_label_y,
            "scale_label_y": scale_label_y,
            "pan_label_y": pan_label_y,
            "rotate_label_y": rotate_label_y,
            "nudge_label_y": nudge_label_y,
            "step_subtitle_y": step_subtitle_y,
            "tilt_hint_y": tilt_hint_y,
            "step_hint_y": step_hint_y,
            "flip_h_center": flip_h_center,
            "flip_v_center": flip_v_center,
            "zoom_minus_rect": zoom_minus_rect,
            "zoom_plus_rect": zoom_plus_rect,
            "rot_minus_rect": rot_minus_rect,
            "rot_plus_rect": rot_plus_rect,
            "rotate_90_ccw_rect": rotate_90_ccw_rect,
            "rotate_90_cw_rect": rotate_90_cw_rect,
            "pan_up_rect": pan_up_rect,
            "pan_left_rect": pan_left_rect,
            "pan_right_rect": pan_right_rect,
            "pan_down_rect": pan_down_rect,
            "step_fine_center": step_fine_center,
            "step_coarse_center": step_coarse_center,
            "reset_rect": reset_rect,
        }

    _vc_probe = _view_control_layout(0, 0)
    _view_column_h = int(_vc_probe["reset_rect"][3]) + int(36 * max(1.0, ui_scale))
    _air = int(28 * max(1.0, ui_scale))
    _head_sub = int(26 * max(1.0, ui_scale))
    _table_tail = int(22 * max(1.0, ui_scale))
    _after_units_pad = int(16 * max(1.0, ui_scale))
    _redetect_gap = int(32 * max(1.0, ui_scale))
    _redetect_block = _after_units_pad + _redetect_gap + max(28, int(30 * max(1.0, ui_scale))) + int(4 * max(1.0, ui_scale))
    _left_column_h = (
        14
        + _air
        + _head_sub
        + len(TABLE_MENU) * row_spacing
        + _table_tail
        + _air
        + _head_sub
        + len(UNIT_MENU) * row_spacing
        + _redetect_block
    )
    estimated_menu_h = (
        panel_drag_handle_h
        + menu_padding
        + max(_left_column_h, _view_column_h)
        + int(54 * max(1.0, ui_scale))
    )

    panel_left_override: Optional[int] = None
    panel_top_override: Optional[int] = None
    panel_dragging = False
    panel_drag_offset_x = 0
    panel_drag_offset_y = 0
    panel_collapsed = False
    # Many macOS/HighGUI builds never deliver EVENT_LBUTTONDBLCLK; detect double-tap in software.
    header_dbl_arm_time: Optional[float] = None
    header_dbl_is_second: bool = False
    header_dbl_start_x: int = 0
    header_dbl_start_y: int = 0
    header_dbl_moved: bool = False
    header_dbl_tap_s = 0.45
    header_dbl_move_px = 6

    zoom_levels = [
        1.00,
        1.03,
        1.06,
        1.10,
        1.15,
        1.20,
        1.26,
        1.33,
        1.41,
        1.50,
        1.60,
        1.75,
        1.90,
        2.10,
        2.30,
        2.55,
        2.85,
        3.20,
        3.60,
        4.00,
    ]
    zoom_idx = 0
    pan_center_src_x = 0.5 * float(w_img - 1)
    pan_center_src_y = 0.5 * float(h_img - 1)

    def _active_labels() -> List[str]:
        return CORNER_LABELS

    def _active_points() -> List[Tuple[float, float]]:
        return corner_points

    def _set_active_points(points: List[Tuple[float, float]]) -> None:
        nonlocal corner_points
        corner_points = points

    def _current_zoom() -> float:
        return float(zoom_levels[zoom_idx])

    # Default to +90 when the incoming frame is portrait.
    view_rotate_deg = 90.0 if h_img > w_img else 0.0

    def _current_view_step() -> Dict[str, float]:
        if view_step_mode == "coarse":
            return {"zoom_delta": 3.0, "rotate_deg": 2.0, "pan_frac_x": 0.03, "pan_frac_y": 0.03}
        return {"zoom_delta": 1.0, "rotate_deg": 0.5, "pan_frac_x": 0.01, "pan_frac_y": 0.01}

    def _clamp_pan_center() -> None:
        nonlocal pan_center_src_x, pan_center_src_y
        pan_center_src_x = float(np.clip(pan_center_src_x, 0.0, float(w_img - 1)))
        pan_center_src_y = float(np.clip(pan_center_src_y, 0.0, float(h_img - 1)))

    def _display_center() -> np.ndarray:
        return np.array([0.5 * float(w_img - 1), 0.5 * float(h_img - 1)], dtype=np.float64)

    def _view_linear() -> np.ndarray:
        flip_m = np.array(
            [
                [-1.0 if flip_view_h else 1.0, 0.0],
                [0.0, -1.0 if flip_view_v else 1.0],
            ],
            dtype=np.float64,
        )
        theta = float(np.deg2rad(view_rotate_deg))
        c = float(np.cos(theta))
        s = float(np.sin(theta))
        rot_m = np.array([[c, -s], [s, c]], dtype=np.float64)
        return _current_zoom() * (rot_m @ flip_m)

    def _view_matrix() -> np.ndarray:
        _clamp_pan_center()
        linear = _view_linear()
        src_center = np.array([pan_center_src_x, pan_center_src_y], dtype=np.float64)
        offset = _display_center() - (linear @ src_center)
        m = np.zeros((2, 3), dtype=np.float32)
        m[:, :2] = linear.astype(np.float32)
        m[:, 2] = offset.astype(np.float32)
        return m

    def _source_to_display(x_src: float, y_src: float) -> Tuple[float, float]:
        m = _view_matrix()
        x_disp = float(m[0, 0] * x_src + m[0, 1] * y_src + m[0, 2])
        y_disp = float(m[1, 0] * x_src + m[1, 1] * y_src + m[1, 2])
        return x_disp, y_disp

    def _display_to_source(x_disp: float, y_disp: float) -> Tuple[float, float]:
        x_disp = float(np.clip(x_disp, 0.0, float(w_img - 1)))
        y_disp = float(np.clip(y_disp, 0.0, float(h_img - 1)))
        m = _view_matrix()
        linear = m[:, :2].astype(np.float64)
        offset = m[:, 2].astype(np.float64)
        src_xy = np.linalg.inv(linear) @ (np.array([x_disp, y_disp], dtype=np.float64) - offset)
        x_src = float(src_xy[0])
        y_src = float(src_xy[1])
        return (
            float(np.clip(x_src, 0.0, float(w_img - 1))),
            float(np.clip(y_src, 0.0, float(h_img - 1))),
        )

    def _render_background() -> np.ndarray:
        m = _view_matrix()
        # Outside the valid source rectangle, BORDER_REPLICATE smears the image edge
        # (looks like a stretched band). Use constant fill so panned/zoomed voids are
        # black — there is no additional live pixels beyond the frame.
        border_val = 0 if img.ndim == 2 else (0, 0, 0)
        return cv2.warpAffine(
            img,
            m,
            (w_img, h_img),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=border_val,
        )

    def _nudge_pan_display(dx_disp: float, dy_disp: float) -> None:
        nonlocal pan_center_src_x, pan_center_src_y
        linear = _view_linear()
        delta_src = np.linalg.inv(linear) @ np.array([dx_disp, dy_disp], dtype=np.float64)
        pan_center_src_x += float(delta_src[0])
        pan_center_src_y += float(delta_src[1])
        _clamp_pan_center()

    def _zoom_step(delta: int, anchor_display_xy: Optional[Tuple[float, float]] = None) -> None:
        nonlocal zoom_idx, pan_center_src_x, pan_center_src_y
        new_idx = int(np.clip(zoom_idx + delta, 0, len(zoom_levels) - 1))
        if new_idx == zoom_idx:
            return
        if anchor_display_xy is None:
            anchor_display_xy = (float(_display_center()[0]), float(_display_center()[1]))
        anchor_disp = np.array(anchor_display_xy, dtype=np.float64)
        anchor_src = np.array(_display_to_source(anchor_disp[0], anchor_disp[1]), dtype=np.float64)
        zoom_idx = new_idx
        linear = _view_linear()
        pan_xy = anchor_src - (np.linalg.inv(linear) @ (anchor_disp - _display_center()))
        pan_center_src_x = float(pan_xy[0])
        pan_center_src_y = float(pan_xy[1])
        _clamp_pan_center()

    def _rotate_step(delta_deg: float, anchor_display_xy: Optional[Tuple[float, float]] = None) -> None:
        nonlocal view_rotate_deg, pan_center_src_x, pan_center_src_y
        if anchor_display_xy is None:
            anchor_display_xy = (float(_display_center()[0]), float(_display_center()[1]))
        anchor_disp = np.array(anchor_display_xy, dtype=np.float64)
        anchor_src = np.array(_display_to_source(anchor_disp[0], anchor_disp[1]), dtype=np.float64)
        view_rotate_deg = float(view_rotate_deg + delta_deg)
        while view_rotate_deg <= -180.0:
            view_rotate_deg += 360.0
        while view_rotate_deg > 180.0:
            view_rotate_deg -= 360.0
        linear = _view_linear()
        pan_xy = anchor_src - (np.linalg.inv(linear) @ (anchor_disp - _display_center()))
        pan_center_src_x = float(pan_xy[0])
        pan_center_src_y = float(pan_xy[1])
        _clamp_pan_center()

    def _reset_view() -> None:
        nonlocal flip_view_h, flip_view_v, zoom_idx, pan_center_src_x, pan_center_src_y, view_rotate_deg
        flip_view_h = False
        flip_view_v = False
        view_rotate_deg = 0.0
        zoom_idx = 0
        pan_center_src_x = 0.5 * float(w_img - 1)
        pan_center_src_y = 0.5 * float(h_img - 1)
        _clamp_pan_center()

    def _menu_layout() -> Dict[str, Any]:
        safe_w = max(200, w_img - 2 * menu_margin)
        safe_h = max(200, h_img - 2 * menu_margin)
        panel_w = min(estimated_menu_w, safe_w)
        panel_h = min(estimated_menu_h, safe_h)
        default_left = max(menu_margin, w_img - panel_w - menu_margin)
        default_top = menu_margin
        if panel_left_override is not None and panel_top_override is not None:
            left = int(panel_left_override)
            top = int(panel_top_override)
        else:
            if len(corner_points) < 4:
                left = default_left
            else:
                anchors = [
                    menu_margin,
                    w_img - panel_w - menu_margin,
                    (w_img - panel_w) // 2,
                ]
                corners_disp = [_source_to_display(float(cx), float(cy)) for cx, cy in corner_points]
                best_left = default_left
                best_dist = -1.0
                for ax in anchors:
                    cand_left = int(np.clip(ax, menu_margin, max(menu_margin, w_img - panel_w - menu_margin)))
                    cand_top = default_top
                    right = cand_left + panel_w
                    bottom = cand_top + panel_h
                    d = min(
                        _distance_sq_point_to_rect(
                            float(cx),
                            float(cy),
                            float(cand_left),
                            float(cand_top),
                            float(right),
                            float(bottom),
                        )
                        for cx, cy in corners_disp
                    )
                    if d > best_dist:
                        best_dist = d
                        best_left = cand_left
                left = best_left
            top = default_top

        left = int(np.clip(left, menu_margin, max(menu_margin, w_img - panel_w - menu_margin)))
        top = int(np.clip(top, menu_margin, max(menu_margin, h_img - panel_h - menu_margin)))
        inner_top = top + panel_drag_handle_h + menu_padding
        inner_left = left + menu_padding
        inner_w = max(120, panel_w - 2 * menu_padding)
        min_col2_w = 240
        col1_w = max(
            128,
            min(int(inner_w * col1_width_frac), max(128, inner_w - col_gap - min_col2_w)),
        )
        col1_left = inner_left
        col2_left = col1_left + col1_w + col_gap
        col1_right = col2_left - 2
        divider_x = col1_left + col1_w + max(4, col_gap // 2)

        air = int(28 * max(1.0, ui_scale))
        head_sub = int(26 * max(1.0, ui_scale))
        table_tail = int(22 * max(1.0, ui_scale))
        setup_heading_baseline = inner_top + 14
        table_heading_y = setup_heading_baseline + air
        table_left = col1_left + 10
        table_top = table_heading_y + head_sub
        last_table_row_y = table_top + (len(TABLE_MENU) - 1) * row_spacing
        table_block_bottom = last_table_row_y + table_tail
        units_heading_y = table_block_bottom + air
        units_left = table_left
        units_top = units_heading_y + head_sub
        view_left = col2_left + 6
        view_top = inner_top + 14 + air + head_sub

        if panel_collapsed:
            panel_h = panel_drag_handle_h + 2
        else:
            probe = _view_control_layout(0, 0)
            right_h = int(probe["reset_rect"][3]) + int(28 * max(1.0, ui_scale))
            rbtn = max(28, int(30 * max(1.0, ui_scale)))
            after_u = int(16 * max(1.0, ui_scale))
            gap_re = int(32 * max(1.0, ui_scale))
            redetect_extra = after_u + gap_re + rbtn + int(4 * max(1.0, ui_scale))
            left_bottom = (
                units_top
                + (len(UNIT_MENU) - 1) * row_spacing
                + redetect_extra
            )
            left_h = left_bottom - inner_top
            twin_stack_h = max(left_h, right_h) + int(8 * max(1.0, ui_scale))
            footer_block = int(52 * max(1.0, ui_scale))
            min_needed_h = panel_drag_handle_h + menu_padding + twin_stack_h + footer_block
            panel_h = int(min(safe_h, max(int(estimated_menu_h), min_needed_h)))
        top = int(np.clip(top, menu_margin, max(menu_margin, h_img - panel_h - menu_margin)))
        inner_top = top + panel_drag_handle_h + menu_padding
        setup_heading_baseline = inner_top + 14
        table_heading_y = setup_heading_baseline + air
        table_top = table_heading_y + head_sub
        last_table_row_y = table_top + (len(TABLE_MENU) - 1) * row_spacing
        table_block_bottom = last_table_row_y + table_tail
        units_heading_y = table_block_bottom + air
        units_top = units_heading_y + head_sub
        view_top = inner_top + 14 + air + head_sub
        drag_handle_rect = (left, top, left + panel_w, top + panel_drag_handle_h)
        rbtn2 = max(28, int(30 * max(1.0, ui_scale)))
        after_u2 = int(16 * max(1.0, ui_scale))
        gap_re2 = int(32 * max(1.0, ui_scale))
        redetect_y1 = (
            float(units_top)
            + (len(UNIT_MENU) - 1) * float(row_spacing)
            + float(after_u2)
            + float(gap_re2)
        )
        redetect_rect = (
            int(table_left) - 2,
            int(redetect_y1),
            int(col1_right) - 2,
            int(redetect_y1 + rbtn2),
        )
        return {
            "panel_left": left,
            "panel_top": top,
            "panel_w": panel_w,
            "panel_h": panel_h,
            "drag_handle_rect": drag_handle_rect,
            "inner_top": inner_top,
            "inner_left": inner_left,
            "col1_left": col1_left,
            "col1_w": col1_w,
            "col1_right": col1_right,
            "col2_left": col2_left,
            "divider_x": divider_x,
            "setup_heading_baseline": setup_heading_baseline,
            "table_heading_y": table_heading_y,
            "units_heading_y": units_heading_y,
            "table_block_bottom": table_block_bottom,
            "table_left": table_left,
            "table_top": table_top,
            "units_left": units_left,
            "units_top": units_top,
            "view_left": view_left,
            "view_top": view_top,
            "redetect_rect": redetect_rect,
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
        selected_color: Tuple[int, int, int] = (102, 178, 255),
    ) -> None:
        ring = (100, 108, 124) if not selected else selected_color
        cv2.circle(canvas, (x, y), radio_radius + 1, ring, 1, lineType=cv2.LINE_AA)
        if selected:
            cv2.circle(canvas, (x, y), max(2, radio_radius - 3), selected_color, -1, lineType=cv2.LINE_AA)
            cv2.circle(canvas, (x, y), max(1, radio_radius - 5), (245, 248, 252), -1, lineType=cv2.LINE_AA)
        cv2.putText(
            canvas,
            label,
            (x + 18, y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (236, 238, 242),
            1,
            cv2.LINE_AA,
        )

    def _draw_button(canvas: np.ndarray, rect: Tuple[int, int, int, int], label: str) -> None:
        x1, y1, x2, y2 = rect
        fill = (54, 58, 70)
        edge = (88, 96, 114)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), fill, -1, lineType=cv2.LINE_AA)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), edge, 1, lineType=cv2.LINE_AA)
        max_w = max(8, (x2 - x1) - 8)
        scale = 0.48
        while scale >= 0.32:
            (tw, th), _bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            if tw <= max_w:
                break
            scale -= 0.04
        tx = x1 + max(4, (x2 - x1 - tw) // 2)
        ty = y1 + (y2 - y1 + th) // 2 - 2
        cv2.putText(canvas, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (238, 240, 245), 1, cv2.LINE_AA)

    def _draw_button_primary(canvas: np.ndarray, rect: Tuple[int, int, int, int], label: str) -> None:
        x1, y1, x2, y2 = rect
        fill = (92, 118, 220)
        edge = (140, 168, 255)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), fill, -1, lineType=cv2.LINE_AA)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), edge, 1, lineType=cv2.LINE_AA)
        max_w = max(8, (x2 - x1) - 10)
        scale = 0.5
        while scale >= 0.34:
            (tw, th), _bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            if tw <= max_w:
                break
            scale -= 0.04
        tx = x1 + max(5, (x2 - x1 - tw) // 2)
        ty = y1 + (y2 - y1 + th) // 2 - 2
        cv2.putText(canvas, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (252, 252, 255), 1, cv2.LINE_AA)

    def _point_in_rect(x: int, y: int, rect: Tuple[int, int, int, int]) -> bool:
        x1, y1, x2, y2 = rect
        return x1 <= x <= x2 and y1 <= y <= y2

    def _refresh_live_frame() -> bool:
        nonlocal img, live_capture
        if live_capture is None:
            try:
                live_capture = _open_capture_for_source(
                    camera=str(args.camera),
                    usb_index=int(args.usb_index),
                    csi_sensor_id=int(args.csi_sensor_id),
                    width=int(args.width),
                    height=int(args.height),
                    framerate=int(args.csi_framerate),
                    flip_method=int(args.csi_flip_method),
                    open_retries=int(args.csi_open_retries),
                )
            except Exception:
                return False
        frame: Optional[np.ndarray] = None
        for _attempt in range(3):
            try:
                frame = _read_preview_frame(live_capture, camera_mode=str(args.camera))
                break
            except Exception:
                try:
                    live_capture.release()
                except Exception:
                    pass
                live_capture = None
                try:
                    live_capture = _open_capture_for_source(
                        camera=str(args.camera),
                        usb_index=int(args.usb_index),
                        csi_sensor_id=int(args.csi_sensor_id),
                        width=int(args.width),
                        height=int(args.height),
                        framerate=int(args.csi_framerate),
                        flip_method=int(args.csi_flip_method),
                        open_retries=int(args.csi_open_retries),
                    )
                except Exception:
                    return False
        if frame is None:
            return False
        if frame.shape[:2] != (h_img, w_img):
            frame = cv2.resize(frame, (w_img, h_img), interpolation=cv2.INTER_LINEAR)
        img = frame
        return True

    def _redetect_corners() -> None:
        nonlocal corner_points
        try:
            corner_points = _estimate_outside_corners(img)
            print("AUTO corners reloaded from current frame.", file=sys.stderr)
        except Exception as exc:
            print(f"Re-detect failed: {exc}", file=sys.stderr)

    def _draw_table_schematic_and_zones() -> None:
        """Reference diagram: tints, grid, break box, strings, side pockets, diamonds, head string, table outline."""
        nonlocal view
        l_m, w_m = _table_dims_m(selected_table_size)
        h_it = _estimate_homography(corner_points, l_m, w_m)
        k_poly_m, foot_quarter_m, (hs_a, hs_b) = _kitchen_foot_and_head_string_m(l_m, w_m)

        def _pm(xym: Tuple[float, float]) -> Tuple[int, int]:
            a, b = _table_m_to_image_xy(h_it, (float(xym[0]), float(xym[1])))
            c, d_ = _source_to_display(a, b)
            return int(c), int(d_)

        for poly_m, fill_bgr, fill_alpha, edge_bgr, tag in (
            (k_poly_m, (50, 140, 60), 0.22, (70, 200, 90), "Kitchen"),
            (foot_quarter_m, (50, 55, 58), 0.12, (80, 88, 98), "Foot quarter"),
        ):
            disp: List[Tuple[int, int]] = []
            for xm, ym in poly_m:
                ix, iy = _table_m_to_image_xy(h_it, (float(xm), float(ym)))
                dx, dy = _source_to_display(ix, iy)
                disp.append((int(dx), int(dy)))
            darr = np.array(disp, dtype=np.int32).reshape((-1, 1, 2))
            overlay = view.copy()
            cv2.fillPoly(overlay, [darr], fill_bgr, lineType=cv2.LINE_AA)
            cv2.addWeighted(overlay, float(fill_alpha), view, 1.0 - float(fill_alpha), 0, view)
            cv2.polylines(view, [darr], isClosed=True, color=edge_bgr, thickness=1, lineType=cv2.LINE_AA)
            cxs = sum(p[0] for p in disp) // max(1, len(disp))
            cys = sum(p[1] for p in disp) // max(1, len(disp))
            tw, _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.34, 1)[0]
            tx, ty = int(cxs - tw // 2), cys + 4
            cv2.putText(
                view, tag, (tx + 1, ty + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (0, 0, 0), 2, cv2.LINE_AA
            )
            cv2.putText(
                view, tag, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (245, 248, 252), 1, cv2.LINE_AA
            )

        if _HAS_TABLE_DIAGRAM and build_table_diagram_m is not None:
            dg = build_table_diagram_m(l_m, w_m)
            for p, q in dg.grid_segments:
                cv2.line(view, _pm(p), _pm(q), (60, 64, 74), 1, lineType=cv2.LINE_AA)
            for p, q in dg.pocket_center_diagonals:
                cv2.line(view, _pm(p), _pm(q), (52, 56, 66), 1, lineType=cv2.LINE_AA)
            bpoly = np.array([_pm(xy) for xy in dg.break_box_m], dtype=np.int32).reshape((-1, 1, 2))
            bov = view.copy()
            cv2.fillPoly(bov, [bpoly], (90, 100, 160), lineType=cv2.LINE_AA)
            cv2.addWeighted(bov, 0.12, view, 0.88, 0, view)
            cv2.polylines(view, [bpoly], isClosed=True, color=(120, 140, 200), thickness=1, lineType=cv2.LINE_AA)
            for seg, col, th in (
                (dg.long_string, (200, 200, 255), 2),
                (dg.transverse_string, (200, 230, 190), 2),
                (dg.foot_string, (180, 160, 210), 2),
            ):
                a, b = seg
                cv2.line(view, _pm(a), _pm(b), col, th, lineType=cv2.LINE_AA)
            for p in dg.side_pockets_m:
                cv2.circle(view, _pm(p), 7, (40, 90, 200), -1, lineType=cv2.LINE_AA)
                cv2.circle(view, _pm(p), 7, (120, 160, 240), 1, lineType=cv2.LINE_AA)
            for p in dg.rail_diamonds_m:
                cv2.circle(view, _pm(p), 3, (220, 225, 235), 1, lineType=cv2.LINE_AA)
            a, b = dg.head_string
            cv2.line(view, _pm(a), _pm(b), (0, 255, 255), 3, lineType=cv2.LINE_AA)
            for cap, anchor in dg.captions:
                u, v = _pm(anchor)
                tw, _ = cv2.getTextSize(cap, cv2.FONT_HERSHEY_SIMPLEX, 0.32, 1)[0]
                x0, y0 = u - tw // 2, v - 4
                cv2.putText(view, cap, (x0 + 1, y0 + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 0, 0), 2, cv2.LINE_AA)
                cv2.putText(view, cap, (x0, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (250, 252, 255), 1, cv2.LINE_AA)
        else:
            p0s = _table_m_to_image_xy(h_it, (float(hs_a[0]), float(hs_a[1])))
            p1s = _table_m_to_image_xy(h_it, (float(hs_b[0]), float(hs_b[1])))
            d0 = _source_to_display(float(p0s[0]), float(p0s[1]))
            d1 = _source_to_display(float(p1s[0]), float(p1s[1]))
            cv2.line(
                view,
                (int(d0[0]), int(d0[1])),
                (int(d1[0]), int(d1[1])),
                (0, 255, 255),
                3,
                lineType=cv2.LINE_AA,
            )
        outline = [corner_points[i] for i in CORNER_OUTLINE_INDEX]
        poly_pts = [(_source_to_display(float(x), float(y))) for x, y in outline]
        poly = np.array([(int(px), int(py)) for px, py in poly_pts], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(view, [poly], isClosed=True, color=(0, 200, 255), thickness=2, lineType=cv2.LINE_AA)

    def redraw() -> None:
        nonlocal view
        view = _render_background()
        layout = _menu_layout()

        if len(corner_points) == 4:
            _draw_table_schematic_and_zones()
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

        panel_left = layout["panel_left"]
        panel_top = layout["panel_top"]
        panel_w = layout["panel_w"]
        panel_h = layout["panel_h"]
        drag_handle_rect = layout["drag_handle_rect"]
        inner_top = int(layout["inner_top"])
        col1_left = int(layout["col1_left"])
        col1_right = int(layout["col1_right"])
        col2_left = int(layout["col2_left"])
        divider_x = int(layout["divider_x"])
        setup_heading_baseline = int(layout["setup_heading_baseline"])
        table_heading_y = int(layout["table_heading_y"])
        units_heading_y = int(layout["units_heading_y"])
        table_block_bottom = int(layout["table_block_bottom"])
        table_left = layout["table_left"]
        table_top = layout["table_top"]
        units_left = layout["units_left"]
        units_top = layout["units_top"]
        view_left = layout["view_left"]
        view_top = layout["view_top"]

        # Cohesive “dashboard” palette (BGR): deep slate shell, cool accent, readable type.
        shell_bg = (28, 32, 40)
        shell_edge = (62, 70, 86)
        panel_bg = (34, 38, 48)
        col_left_fill = (40, 44, 54)
        col_right_fill = (38, 42, 52)
        header_bg = (42, 48, 60)
        header_rim = (28, 34, 44)
        accent = (102, 178, 255)
        accent_soft = (78, 130, 210)
        text_hi = (248, 250, 252)
        text_mid = (200, 206, 216)
        muted = (132, 140, 154)
        line_soft = (64, 72, 88)

        def _micro_label(img: np.ndarray, x: int, y: int, s: str) -> None:
            cv2.putText(
                img,
                s,
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                muted,
                1,
                cv2.LINE_AA,
            )

        cv2.rectangle(
            view,
            (panel_left, panel_top),
            (panel_left + panel_w, panel_top + panel_h),
            shell_bg,
            -1,
            lineType=cv2.LINE_AA,
        )
        cv2.rectangle(
            view,
            (panel_left + 1, panel_top + 1),
            (panel_left + panel_w - 1, panel_top + panel_h - 1),
            panel_bg,
            -1,
            lineType=cv2.LINE_AA,
        )
        cv2.rectangle(
            view,
            (panel_left, panel_top),
            (panel_left + panel_w, panel_top + panel_h),
            shell_edge,
            1,
            lineType=cv2.LINE_AA,
        )
        hx1, hy1, hx2, hy2 = drag_handle_rect
        cv2.rectangle(view, (hx1, hy1), (hx2, hy2), header_rim, -1, lineType=cv2.LINE_AA)
        cv2.rectangle(view, (hx1 + 3, hy1), (hx2, hy2), header_bg, -1, lineType=cv2.LINE_AA)
        cv2.line(view, (hx1 + 2, hy1 + 2), (hx1 + 2, hy2 - 2), accent, 2, lineType=cv2.LINE_AA)
        cv2.putText(
            view,
            "Calibration",
            (hx1 + 14, hy1 + 26),
            cv2.FONT_HERSHEY_DUPLEX,
            0.58,
            text_hi,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "Drag header   r corners   Enter save   q Esc",
            (hx1 + 14, hy2 - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            muted,
            1,
            cv2.LINE_AA,
        )

        if panel_collapsed:
            cv2.putText(
                view,
                "Double-click header to expand",
                (panel_left + 12, panel_top + panel_h - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                muted,
                1,
                cv2.LINE_AA,
            )
            return

        inner_bottom = panel_top + panel_h - menu_padding
        cv2.rectangle(
            view,
            (col1_left - 6, inner_top - 4),
            (divider_x - 6, inner_bottom),
            col_left_fill,
            -1,
            lineType=cv2.LINE_AA,
        )
        cv2.rectangle(
            view,
            (divider_x + 6, inner_top - 4),
            (panel_left + panel_w - menu_padding, inner_bottom),
            col_right_fill,
            -1,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            view,
            (divider_x, inner_top - 2),
            (divider_x, inner_bottom),
            line_soft,
            1,
            lineType=cv2.LINE_AA,
        )

        cv2.putText(
            view,
            "SETUP",
            (col1_left, setup_heading_baseline),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            text_mid,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "VIEW",
            (col2_left, setup_heading_baseline),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            text_mid,
            1,
            cv2.LINE_AA,
        )

        def _fit_text_width(text: str, scale: float, max_w: int) -> str:
            t = text
            while len(t) > 1:
                w, _ = cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0]
                if w <= max_w:
                    return t
                t = t[:-1]
            return t

        text_max = max(60, col1_right - table_left - 22)
        _micro_label(view, table_left, table_heading_y - 2, "TABLE")
        cv2.putText(
            view,
            "Presets",
            (table_left, table_heading_y + 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            text_mid,
            1,
            cv2.LINE_AA,
        )
        rx_strip1 = int(col1_left - 2)
        rx_strip2 = int(col1_right + 2)
        for idx, name in enumerate(TABLE_MENU, start=1):
            row_y = table_top + (idx - 1) * row_spacing
            dims = TABLE_PRESETS_M[name]
            marker = " *" if name == detected_default_table_size else ""
            line1 = f"{idx}. {_table_size_label(name)}{marker}"
            line2 = _format_dims(dims[0], dims[1], selected_units)
            line2 = _fit_text_width(line2, 0.38, text_max)
            sel = name == selected_table_size
            ring = accent if sel else (100, 108, 124)
            cv2.circle(view, (table_left, row_y), radio_radius + 1, ring, 1, lineType=cv2.LINE_AA)
            if sel:
                cv2.circle(
                    view,
                    (table_left, row_y),
                    max(2, radio_radius - 3),
                    accent,
                    -1,
                    lineType=cv2.LINE_AA,
                )
                cv2.circle(
                    view,
                    (table_left, row_y),
                    max(1, radio_radius - 5),
                    (248, 250, 252),
                    -1,
                    lineType=cv2.LINE_AA,
                )
            cv2.putText(
                view,
                line1,
                (table_left + 18, row_y + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                text_hi,
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                view,
                line2,
                (table_left + 18, row_y + 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                muted,
                1,
                cv2.LINE_AA,
            )

        div_y = (table_block_bottom + units_heading_y) // 2
        cv2.line(
            view,
            (rx_strip1, div_y),
            (rx_strip2, div_y),
            line_soft,
            1,
            lineType=cv2.LINE_AA,
        )

        _micro_label(view, units_left, units_heading_y - 2, "OUTPUT")
        cv2.putText(
            view,
            "Units",
            (units_left, units_heading_y + 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            text_mid,
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
                label=f"{idx}. {unit_name.capitalize()}",
                selected_color=accent,
            )

        last_unit_row_y = int(units_top + (len(UNIT_MENU) - 1) * row_spacing)
        rr = layout.get("redetect_rect")
        if isinstance(rr, tuple) and len(rr) == 4:
            sep_y = (last_unit_row_y + int(rr[1])) // 2
            cv2.line(
                view,
                (rx_strip1, sep_y),
                (rx_strip2, sep_y),
                line_soft,
                1,
                lineType=cv2.LINE_AA,
            )
            _draw_button_primary(view, rr, "Re-detect")
            _micro_label(view, int(rr[0]), int(rr[3]) + 12, "Auto corner pockets  (same as r)")

        controls = _view_control_layout(int(view_left), int(view_top))
        flip_h_center = controls["flip_h_center"]
        flip_v_center = controls["flip_v_center"]
        _micro_label(view, view_left, int(controls["orient_label_y"]), "ORIENTATION")
        _draw_radio(
            view,
            int(flip_h_center[0]),
            int(flip_h_center[1]),
            selected=flip_view_h,
            label="Flip H",
            selected_color=accent_soft,
        )
        _draw_radio(
            view,
            int(flip_v_center[0]),
            int(flip_v_center[1]),
            selected=flip_view_v,
            label="Flip V",
            selected_color=accent_soft,
        )

        _zm = controls["zoom_minus_rect"]
        _zp = controls["zoom_plus_rect"]
        _micro_label(view, view_left, int(controls["scale_label_y"]), "SCALE")
        _draw_button(view, _zm, "-")
        _draw_button(view, _zp, "+")
        cv2.putText(
            view,
            f"{_current_zoom():.2f}x",
            (_zp[2] + 10, int((_zm[1] + _zm[3]) // 2 + 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            text_hi,
            1,
            cv2.LINE_AA,
        )

        _micro_label(view, view_left, int(controls["pan_label_y"]), "PAN")

        def _draw_pan_tile(canvas: np.ndarray, rect: Tuple[int, int, int, int], direction: str) -> None:
            x1, y1, x2, y2 = rect
            fill = (54, 58, 70)
            edge = (88, 96, 114)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), fill, -1, lineType=cv2.LINE_AA)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), edge, 1, lineType=cv2.LINE_AA)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            inset = max(6, min(x2 - x1, y2 - y1) // 4)
            col = (230, 235, 245)
            if direction == "u":
                pts = np.array([[cx, y1 + inset], [x2 - inset, y2 - inset], [x1 + inset, y2 - inset]], dtype=np.int32)
                cv2.fillConvexPoly(canvas, pts, col, lineType=cv2.LINE_AA)
            elif direction == "d":
                pts = np.array([[cx, y2 - inset], [x1 + inset, y1 + inset], [x2 - inset, y1 + inset]], dtype=np.int32)
                cv2.fillConvexPoly(canvas, pts, col, lineType=cv2.LINE_AA)
            elif direction == "l":
                pts = np.array([[x1 + inset, cy], [x2 - inset, y1 + inset], [x2 - inset, y2 - inset]], dtype=np.int32)
                cv2.fillConvexPoly(canvas, pts, col, lineType=cv2.LINE_AA)
            else:
                pts = np.array([[x2 - inset, cy], [x1 + inset, y1 + inset], [x1 + inset, y2 - inset]], dtype=np.int32)
                cv2.fillConvexPoly(canvas, pts, col, lineType=cv2.LINE_AA)

        _draw_pan_tile(view, controls["pan_up_rect"], "u")
        _draw_pan_tile(view, controls["pan_left_rect"], "l")
        _draw_pan_tile(view, controls["pan_right_rect"], "r")
        _draw_pan_tile(view, controls["pan_down_rect"], "d")

        _micro_label(view, view_left, int(controls["rotate_label_y"]), "ROTATE")
        _draw_button(view, controls["rot_minus_rect"], "-")
        _draw_button(view, controls["rot_plus_rect"], "+")
        _draw_button(view, controls["rotate_90_ccw_rect"], "-90")
        _draw_button(view, controls["rotate_90_cw_rect"], "+90")
        cv2.putText(
            view,
            f"Tilt {view_rotate_deg:+.0f} deg",
            (view_left, int(controls["tilt_hint_y"])),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            text_mid,
            1,
            cv2.LINE_AA,
        )
        step = _current_view_step()
        step_fine_center = controls["step_fine_center"]
        step_coarse_center = controls["step_coarse_center"]
        _micro_label(view, view_left, int(controls["nudge_label_y"]), "NUDGE")
        cv2.putText(
            view,
            "Fine / Coarse",
            (view_left, int(controls["step_subtitle_y"])),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            text_mid,
            1,
            cv2.LINE_AA,
        )
        _draw_radio(
            view,
            int(step_fine_center[0]),
            int(step_fine_center[1]),
            selected=(view_step_mode == "fine"),
            label="Fine",
            selected_color=accent,
        )
        _draw_radio(
            view,
            int(step_coarse_center[0]),
            int(step_coarse_center[1]),
            selected=(view_step_mode == "coarse"),
            label="Coarse",
            selected_color=accent,
        )
        cv2.putText(
            view,
            f"Rotate {step['rotate_deg']:.1f} deg   Pan {100.0 * step['pan_frac_x']:.1f}%",
            (view_left, int(controls["step_hint_y"])),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            muted,
            1,
            cv2.LINE_AA,
        )
        _draw_button_primary(view, controls["reset_rect"], "Reset view")

        foot_y1 = panel_top + panel_h - 40
        foot_y2 = panel_top + panel_h - 18
        cv2.rectangle(
            view,
            (panel_left + 2, foot_y1 - 18),
            (panel_left + panel_w - 2, panel_top + panel_h - 2),
            header_rim,
            -1,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            view,
            (panel_left + 10, foot_y1 - 10),
            (panel_left + panel_w - 10, foot_y1 - 10),
            line_soft,
            1,
            lineType=cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "Video: Kitchen=head rail  head string; foot quarter; cyan=head string  (L0.25 default)",
            (panel_left + 12, foot_y1),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.30,
            accent,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            view,
            "Drag yellow handles to each corner pocket inner intersection",
            (panel_left + 12, foot_y2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            muted,
            1,
            cv2.LINE_AA,
        )

    def _hit_table_option(x: int, y: int) -> Optional[str]:
        if panel_collapsed:
            return None
        layout = _menu_layout()
        table_top = layout["table_top"]
        col1_right = int(layout["col1_right"])
        row_half = max(14, row_spacing // 2 - 1)
        for idx, name in enumerate(TABLE_MENU, start=1):
            row_y = table_top + (idx - 1) * row_spacing
            if int(layout["col1_left"]) - 10 <= x <= col1_right and abs(y - row_y) <= row_half:
                return name
        return None

    def _hit_units_option(x: int, y: int) -> Optional[str]:
        if panel_collapsed:
            return None
        layout = _menu_layout()
        units_top = layout["units_top"]
        col1_right = int(layout["col1_right"])
        row_half = max(14, row_spacing // 2 - 1)
        for idx, name in enumerate(UNIT_MENU, start=1):
            row_y = units_top + (idx - 1) * row_spacing
            if int(layout["col1_left"]) - 10 <= x <= col1_right and abs(y - row_y) <= row_half:
                return name
        return None

    def _hit_redetect(x: int, y: int) -> bool:
        if panel_collapsed:
            return False
        layout = _menu_layout()
        rr = layout.get("redetect_rect")
        if not isinstance(rr, tuple) or len(rr) != 4:
            return False
        return _point_in_rect(x, y, rr)

    def _hit_view_control(x: int, y: int) -> Optional[str]:
        if panel_collapsed:
            return None
        layout = _menu_layout()
        controls = _view_control_layout(int(layout["view_left"]), int(layout["view_top"]))
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
        if _point_in_rect(x, y, controls["rot_minus_rect"]):
            return "rot_left"
        if _point_in_rect(x, y, controls["rot_plus_rect"]):
            return "rot_right"
        if _point_in_rect(x, y, controls["rotate_90_ccw_rect"]):
            return "rot_90_ccw"
        if _point_in_rect(x, y, controls["rotate_90_cw_rect"]):
            return "rot_90_cw"
        if _point_in_rect(x, y, controls["pan_up_rect"]):
            return "pan_up"
        if _point_in_rect(x, y, controls["pan_left_rect"]):
            return "pan_left"
        if _point_in_rect(x, y, controls["pan_right_rect"]):
            return "pan_right"
        if _point_in_rect(x, y, controls["pan_down_rect"]):
            return "pan_down"
        step_fine_center = controls["step_fine_center"]
        step_coarse_center = controls["step_coarse_center"]
        if abs(x - int(step_fine_center[0])) <= radio_hit_radius and abs(y - int(step_fine_center[1])) <= radio_hit_radius:
            return "step_fine"
        if abs(x - int(step_coarse_center[0])) <= radio_hit_radius and abs(y - int(step_coarse_center[1])) <= radio_hit_radius:
            return "step_coarse"
        if _point_in_rect(x, y, controls["reset_rect"]):
            return "view_reset"
        return None

    def _hit_panel_drag_handle(x: int, y: int) -> bool:
        layout = _menu_layout()
        return _point_in_rect(x, y, layout["drag_handle_rect"])

    def on_mouse(event, x, y, _flags, _userdata) -> None:
        nonlocal selected_table_size, selected_units, active_point_idx, dragging
        nonlocal flip_view_h, flip_view_v, view_step_mode
        nonlocal panel_dragging, panel_drag_offset_x, panel_drag_offset_y
        nonlocal panel_left_override, panel_top_override, panel_collapsed
        nonlocal header_dbl_arm_time, header_dbl_is_second, header_dbl_moved
        nonlocal header_dbl_start_x, header_dbl_start_y
        nonlocal corner_points
        if event == cv2.EVENT_LBUTTONDBLCLK:
            if _hit_panel_drag_handle(x, y):
                header_dbl_arm_time = None
                panel_collapsed = not panel_collapsed
                panel_dragging = False
                redraw()
                return
        if event == cv2.EVENT_LBUTTONDOWN:
            if not _hit_panel_drag_handle(x, y):
                header_dbl_arm_time = None
            if _hit_panel_drag_handle(x, y):
                now = time.time()
                if (
                    header_dbl_arm_time is not None
                    and (now - header_dbl_arm_time) > header_dbl_tap_s
                ):
                    header_dbl_arm_time = None
                is_second = bool(
                    header_dbl_arm_time is not None
                    and 0.0 < (now - float(header_dbl_arm_time)) < header_dbl_tap_s
                )
                if is_second:
                    header_dbl_arm_time = None
                header_dbl_is_second = is_second
                header_dbl_start_x, header_dbl_start_y = int(x), int(y)
                header_dbl_moved = False
                layout = _menu_layout()
                x1, y1, _x2, _y2 = layout["drag_handle_rect"]
                panel_dragging = True
                panel_drag_offset_x = int(x - x1)
                panel_drag_offset_y = int(y - y1)
                return
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
            if _hit_redetect(x, y):
                _redetect_corners()
                redraw()
                return
            hit_view = _hit_view_control(x, y)
            if hit_view is not None:
                step = _current_view_step()
                zoom_delta = int(round(step["zoom_delta"]))
                rotate_delta = float(step["rotate_deg"])
                pan_dx = float(step["pan_frac_x"]) * float(w_img)
                pan_dy = float(step["pan_frac_y"]) * float(h_img)
                if hit_view == "flip_h":
                    flip_view_h = not flip_view_h
                    _clamp_pan_center()
                elif hit_view == "flip_v":
                    flip_view_v = not flip_view_v
                    _clamp_pan_center()
                elif hit_view == "zoom_in":
                    _zoom_step(+zoom_delta)
                elif hit_view == "zoom_out":
                    _zoom_step(-zoom_delta)
                elif hit_view == "rot_left":
                    _rotate_step(-rotate_delta)
                elif hit_view == "rot_right":
                    _rotate_step(+rotate_delta)
                elif hit_view == "rot_90_ccw":
                    _rotate_step(-90.0)
                elif hit_view == "rot_90_cw":
                    _rotate_step(+90.0)
                elif hit_view == "pan_up":
                    _nudge_pan_display(0.0, -pan_dy)
                elif hit_view == "pan_left":
                    _nudge_pan_display(-pan_dx, 0.0)
                elif hit_view == "pan_right":
                    _nudge_pan_display(+pan_dx, 0.0)
                elif hit_view == "pan_down":
                    _nudge_pan_display(0.0, +pan_dy)
                elif hit_view == "step_fine":
                    view_step_mode = "fine"
                elif hit_view == "step_coarse":
                    view_step_mode = "coarse"
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
        elif event == cv2.EVENT_MOUSEMOVE:
            if panel_dragging:
                dx = int(x) - header_dbl_start_x
                dy = int(y) - header_dbl_start_y
                d2 = dx * dx + dy * dy
                if d2 > header_dbl_move_px * header_dbl_move_px:
                    header_dbl_moved = True
                layout = _menu_layout()
                panel_w = int(layout["panel_w"])
                panel_h = int(layout["panel_h"])
                min_left = int(menu_margin)
                max_left = int(max(menu_margin, w_img - panel_w - menu_margin))
                min_top = int(menu_margin)
                max_top = int(max(menu_margin, h_img - panel_h - menu_margin))
                panel_left_override = int(np.clip(x - panel_drag_offset_x, min_left, max_left))
                panel_top_override = int(np.clip(y - panel_drag_offset_y, min_top, max_top))
                redraw()
                return
            if dragging and active_point_idx is not None:
                pts = _active_points()
                if 0 <= active_point_idx < len(pts):
                    src_x, src_y = _display_to_source(float(x), float(y))
                    pts[active_point_idx] = (src_x, src_y)
                    _set_active_points(pts)
                    redraw()
        elif event == cv2.EVENT_LBUTTONUP:
            if panel_dragging:
                if header_dbl_is_second and not header_dbl_moved:
                    header_dbl_arm_time = None
                    panel_collapsed = not panel_collapsed
                    redraw()
                elif (not header_dbl_is_second) and (not header_dbl_moved):
                    header_dbl_arm_time = time.time()
                else:
                    header_dbl_arm_time = None
            header_dbl_is_second = False
            header_dbl_moved = False
            panel_dragging = False
            dragging = False
            active_point_idx = None

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_mouse)
    redraw()
    cv2.imshow(win, view)
    _apply_fullscreen_window(win)

    while True:
        _refresh_live_frame()
        redraw()
        cv2.imshow(win, view)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            if live_capture is not None:
                live_capture.release()
            cv2.destroyAllWindows()
            print("Cancelled.", file=sys.stderr)
            raise SystemExit(1)
        if key in (ord("r"), ord("a")):
            _redetect_corners()
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
        if key in (ord("g"),):
            view_step_mode = "coarse" if view_step_mode == "fine" else "fine"
            redraw()
        step = _current_view_step()
        zoom_delta = int(round(step["zoom_delta"]))
        rotate_delta = float(step["rotate_deg"])
        pan_dx = float(step["pan_frac_x"]) * float(w_img)
        pan_dy = float(step["pan_frac_y"]) * float(h_img)
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
            _zoom_step(+zoom_delta)
            redraw()
        if key in (ord("-"), ord("_"), ord("[")):
            _zoom_step(-zoom_delta)
            redraw()
        if key in (ord("z"), ord(",")):
            _rotate_step(-rotate_delta)
            redraw()
        if key in (ord("x"), ord(".")):
            _rotate_step(+rotate_delta)
            redraw()
        if key in (ord("o"),):
            _rotate_step(-90.0)
            redraw()
        if key in (ord("p"),):
            _rotate_step(+90.0)
            redraw()
        if key in (81, ord("j")):  # left arrow or j
            _nudge_pan_display(-pan_dx, 0.0)
            redraw()
        if key in (83, ord("l")):  # right arrow or l
            _nudge_pan_display(+pan_dx, 0.0)
            redraw()
        if key in (82, ord("i")):  # up arrow or i
            _nudge_pan_display(0.0, -pan_dy)
            redraw()
        if key in (84, ord("k")):  # down arrow or k
            _nudge_pan_display(0.0, +pan_dy)
            redraw()
        if key in (13, 10):
            if len(corner_points) != 4:
                print("Need exactly 4 outside corner points before saving.")
                continue
            break

    cv2.destroyAllWindows()
    if live_capture is not None:
        live_capture.release()

    table_length_m, table_width_m = _table_dims_m(selected_table_size)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_with_edge_helpers = False

    if _HAS_EDGE_AUTOCAL:
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
            side_pockets_px=None,
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
    if not wrote_with_edge_helpers:
        print("Saved using standalone calibration writer.")


if __name__ == "__main__":
    main()
