#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PROJECT_ROOT="${PROJECT_ROOT:-/home/$USER/Billiards-AI}"
CALIB_SCRIPT="${CALIB_SCRIPT:-$PROJECT_ROOT/scripts/calib_click.py}"
CALIB_OUT="${CALIB_OUT:-$PROJECT_ROOT/calibration.json}"

# Default camera: macOS/typical dev → USB; Jetson/embedded → CSI (Argus, GStreamer).
# Override with CAMERA_SOURCE=... (e.g. csi, usb) or pass flags through to calib_click.py
if [[ -z "${CAMERA_SOURCE:-}" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    CAMERA_SOURCE=usb
  else
    CAMERA_SOURCE=csi
  fi
fi
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-6}"
CSI_FRAMERATE="${CSI_FRAMERATE:-30}"
CSI_OPEN_RETRIES="${CSI_OPEN_RETRIES:-8}"
FRAME_WIDTH="${FRAME_WIDTH:-1280}"
FRAME_HEIGHT="${FRAME_HEIGHT:-720}"
UNITS="${UNITS:-imperial}"
POCKET_RADIUS_M="${POCKET_RADIUS_M:-0.07}"
# Optional YOLO ONNX (`pockets` class): auto-used when `models/model.onnx` exists unless overridden.
POCKET_ONNX="${POCKET_ONNX:-}"
POCKET_CLASS_MAP="${POCKET_CLASS_MAP:-}"
POCKET_MIN_CONF="${POCKET_MIN_CONF:-}"
RACK_STYLE="${RACK_STYLE:-8ball}"

usage() {
  cat <<'EOF'
Single-command calibration startup.

Environment overrides (optional):
  PROJECT_ROOT      (default: /home/$USER/Billiards-AI)
  CALIB_SCRIPT      (default: $PROJECT_ROOT/scripts/calib_click.py)
  CALIB_OUT         (default: $PROJECT_ROOT/calibration.json)
  CAMERA_SOURCE     (default: csi)
  CSI_SENSOR_ID     (default: 0)
  CSI_FLIP_METHOD   (default: 6)
  CSI_FRAMERATE     (default: 30)
  CSI_OPEN_RETRIES  (default: 8; Argus CSI reopen attempts in calib_click.py)
  SKIP_CSI_PREFLIGHT  (if non-empty, skip Jetson CSI gst-launch probe before GUI)
  CALIB_NO_FULLSCREEN (if set to 1, pass --no-fullscreen: windowed OpenCV; fixes some Jetson/GTK mouse maps)
  FRAME_WIDTH       (default: 1280)
  FRAME_HEIGHT      (default: 720)
  UNITS             (default: imperial)
  POCKET_RADIUS_M   (default: 0.07)
  POCKET_ONNX       (optional; explicit path — empty uses MODEL_PATH or models/model.onnx if present)
  POCKET_CLASS_MAP  (optional; default: \$PROJECT_ROOT/models/class_map.json)
  POCKET_MIN_CONF   (optional; forwarded as --pocket-min-conf)
  RACK_STYLE        (default: 8ball; also 9ball — schematic rack overlay in calib_click)
  CALIB_OVERLAY_JSON  (default: \$PROJECT_ROOT/config/calib_overlay.json when present; break_box + label x_L,y_W anchors; GUI key e edits labels)

Example:
  bash /home/$USER/Billiards-AI/scripts/start_calibration.sh

Optional extra arguments are forwarded to calib_click.py (later flags override earlier ones), e.g.:
  bash /home/$USER/Billiards-AI/scripts/start_calibration.sh --width 640 --height 480 --csi-framerate 15
  bash /home/$USER/Billiards-AI/scripts/start_calibration.sh --camera 0
EOF
}

assert_calibration_gui_features() {
  require_file "$CALIB_SCRIPT"
  /usr/bin/python3 - "$CALIB_SCRIPT" <<'PY'
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
text = target.read_text(encoding="utf-8", errors="ignore")
# Assert wiring for view transforms (labels change with UI polish; keys stay stable).
required_tokens = [
    "_rotate_step",
    "_nudge_pan_display",
    'controls["rot_minus_rect"]',
    'controls["rot_plus_rect"]',
    "view_rotate_deg",
    "flip_view_h",
    "flip_view_v",
]
missing = [token for token in required_tokens if token not in text]
if missing:
    print(
        "ERROR: Local calib_click.py is missing expected GUI view controls: "
        + ", ".join(missing),
        file=sys.stderr,
    )
    print(
        "Fix local disk file first, then rerun start_calibration.sh.",
        file=sys.stderr,
    )
    raise SystemExit(2)
print("Calibration GUI feature check: OK")
PY
}

_venv_cv_numpy_check_relaxed() {
  # macOS and generic USB: pip opencv often reports GStreamer: NO; only require NumPy<2 + import.
  local py
  py="$1"
  if "$py" - <<'PY'
import sys
try:
    import numpy as np
    import cv2  # noqa: F401
except Exception:
    sys.exit(1)
if int(str(np.__version__).split(".")[0]) >= 2:
    sys.exit(2)
sys.exit(0)
PY
  then
    return 0
  fi
  return 1
}

_venv_cv_numpy_check_csi() {
  # Jetson CSI / calibration: venv must see GStreamer: YES in OpenCV build.
  local py
  py="$1"
  if "$py" - <<'PY'
import sys
try:
    import numpy  # noqa: F401
    import cv2
except Exception:
    sys.exit(1)
try:
    import numpy as np
    if int(str(np.__version__).split(".")[0]) >= 2:
        sys.exit(2)
except Exception:
    sys.exit(2)
info = cv2.getBuildInformation()
if "GStreamer:                   YES" not in info:
    sys.exit(3)
sys.exit(0)
PY
  then
    return 0
  fi
  return 1
}

_venv_cv_numpy_check_after_repair() {
  if [[ "$(_uname)" == "Darwin" ]]; then
    _venv_cv_numpy_check_relaxed "$1" && return 0
  else
    # After numpy reinstall, re-run full GStreamer check on Linux
    _venv_cv_numpy_check_csi "$1" && return 0
  fi
  return 1
}

_uname() {
  uname -s
}

_print_macos_cv2_help() {
  echo "On macOS, pip 'opencv-python' does not use GStreamer; that is normal for USB webcams." >&2
  echo "This script only requires: Python venv, NumPy<2, and 'import cv2' from the venv." >&2
  echo "Try:" >&2
  echo "  source \"$VENV_PATH/bin/activate\"" >&2
  echo "  python -m pip install --upgrade --force-reinstall \"numpy<2\"" >&2
  echo "  python -m pip install -U opencv-python" >&2
  echo "Grant Camera (and if prompted, Microphone) to Terminal, iTerm, or VS Code, then run start_calibration again." >&2
  echo "The script defaults to CAMERA_SOURCE=usb on Darwin (use CSI-style flags only on Jetson)." >&2
}

_print_linux_csi_gst_help() {
  echo "On Linux/Jetson (CSI + GStreamer), if the check reported GStreamer: NO, remove pip OpenCV" >&2
  echo "and use system packages, or a venv with --system-site-packages. Example:" >&2
  echo "  source \"$VENV_PATH/bin/activate\"" >&2
  echo "  python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless" >&2
  echo "  sudo /usr/bin/apt-get install -y python3-opencv python3-gst-1.0 gstreamer1.0-tools" >&2
  echo "  python3 -m venv --system-site-packages \"$VENV_PATH\"" >&2
  echo "NumPy<2 only:" >&2
  echo "  cd \"$PROJECT_ROOT\"" >&2
  echo "  source \"$VENV_PATH/bin/activate\"" >&2
  echo "  python -m pip install --upgrade --force-reinstall \"numpy<2\"" >&2
}

ensure_cv2_numpy_abi() {
  local py
  py="$(python_bin)"
  # System python3 can load distro cv2 while the venv has pip wheels; we probe the venv only.

  if [[ "$(_uname)" == "Darwin" ]]; then
    if _venv_cv_numpy_check_relaxed "$py"; then
      echo "OpenCV/NumPy check: OK (macOS — NumPy<2 and venv cv2; GStreamer not required for USB)"
      return 0
    fi
  else
    if _venv_cv_numpy_check_csi "$py"; then
      echo "OpenCV/NumPy ABI check: OK (venv cv2, GStreamer enabled)"
      return 0
    fi
  fi

  echo "OpenCV/NumPy import failed; attempting NumPy repair (numpy<2) for OpenCV wheel compatibility..."
  "$py" -m pip install --upgrade --force-reinstall "numpy<2"

  if _venv_cv_numpy_check_after_repair "$py"; then
    if [[ "$(_uname)" == "Darwin" ]]; then
      echo "OpenCV/NumPy check after repair: OK (macOS)"
    else
      echo "OpenCV/NumPy ABI check after repair: OK (venv cv2, GStreamer enabled)"
    fi
    return 0
  fi

  echo "ERROR: venv OpenCV/NumPy check failed after repair." >&2
  if [[ "$(_uname)" == "Darwin" ]]; then
    _print_macos_cv2_help
  else
    _print_linux_csi_gst_help
  fi
  echo "Then rerun start_calibration.sh." >&2
  exit 2
}

_print_csi_preflight_failure() {
  local blob="$1"
  echo "" >&2
  echo "================================================================" >&2
  echo "CSI camera: Argus did not deliver frames (preflight failed)." >&2
  echo "The calibration GUI was not started — fix CSI before retrying." >&2
  echo "================================================================" >&2
  echo "" >&2
  echo "Run in this order (hardware first, then software):" >&2
  echo "  1) Re-seat the CSI ribbon (correct orientation, full latch)." >&2
  echo "  2) sudo systemctl restart nvargus-daemon && sleep 2" >&2
  echo "  3) bash \"$PROJECT_ROOT/scripts/jetson_csi_setup.sh\"" >&2
  echo "  4) Second Argus camera: CSI_SENSOR_ID=1 only if a second sensor probed OK (see dmesg). If one CSI sensor failed probe, Argus may only expose index 0 — use CSI_SENSOR_ID=0." >&2
  echo "  5) Lighter mode: bash \"$PROJECT_ROOT/scripts/start_calibration.sh\" --width 640 --height 480 --csi-framerate 15" >&2
  echo "  6) USB instead (if you have /dev/video0): bash \"$PROJECT_ROOT/scripts/start_calibration.sh\" --camera 0" >&2
  echo "  7) Cold boot; then: sudo dmesg | grep -iE 'imx|tegra|nv_camera'" >&2
  echo "" >&2
  echo "To skip this probe (only if you know Argus is flaky in your setup):" >&2
  echo "  SKIP_CSI_PREFLIGHT=1 bash \"$PROJECT_ROOT/scripts/start_calibration.sh\"" >&2
  echo "" >&2
  echo "Last gst-launch lines:" >&2
  echo "$blob" | /usr/bin/tail -n 24 >&2
}

_preflight_csi_argus() {
  if [[ -n "${SKIP_CSI_PREFLIGHT:-}" ]]; then
    echo "Skipping CSI preflight (SKIP_CSI_PREFLIGHT is set)."
    return 0
  fi
  if [[ "$(uname -s)" != "Linux" ]]; then
    return 0
  fi
  local m
  m="$(uname -m)"
  if [[ "$m" != "aarch64" && "$m" != "arm64" ]]; then
    return 0
  fi
  if [[ "${CAMERA_SOURCE:-csi}" != "csi" ]]; then
    return 0
  fi

  echo "CSI preflight: nvarguscamerasrc sensor-id=$CSI_SENSOR_ID (one buffer)…"
  local _out
  set +e
  _out="$(run_with_timeout 15 /usr/bin/gst-launch-1.0 -e nvarguscamerasrc sensor-id="$CSI_SENSOR_ID" num-buffers=1 ! fakesink 2>&1)"
  set -e

  if echo "$_out" | /usr/bin/grep -qiE "Invalid camera device specified|max index"; then
    echo "" >&2
    echo "Argus: no camera at this index (often '0 max index' = only one sensor enumerated)." >&2
    echo "  sensor-id is the Argus camera list (0..N-1 for working sensors), not 'CAM1' vs 'CAM0'." >&2
    echo "  If a second CSI module failed driver probe (e.g. imx477 i2c -121 in dmesg), only index 0 exists — use CSI_SENSOR_ID=0." >&2
    _print_csi_preflight_failure "$_out"
    exit 3
  fi
  if echo "$_out" | /usr/bin/grep -qi "No cameras available"; then
    _print_csi_preflight_failure "$_out"
    exit 3
  fi
  if echo "$_out" | /usr/bin/grep -qiE "Failed to create CaptureSession|No EGLDisplay|ERROR.*nvargus"; then
    _print_csi_preflight_failure "$_out"
    exit 3
  fi
  echo "CSI preflight: OK"
}

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
    usage
    exit 0
  fi

  cd_root
  activate_venv
  ensure_cv2_numpy_abi
  assert_calibration_gui_features
  _preflight_csi_argus

  echo "Launching calibration GUI from: $CALIB_SCRIPT"
  echo "Output calibration path: $CALIB_OUT"
  CALIB_OVERLAY_JSON="${CALIB_OVERLAY_JSON:-$PROJECT_ROOT/config/calib_overlay.json}"
  if [[ -f "$CALIB_OVERLAY_JSON" ]]; then
    echo "Overlay config (label positions, break box): $CALIB_OVERLAY_JSON"
  else
    echo "Note: no overlay JSON at $CALIB_OVERLAY_JSON (optional; calib_click uses built-in table-geometry label positions only)."
  fi
  pocket_extra=()
  if [[ -n "$POCKET_ONNX" ]]; then
    pocket_extra+=(--pocket-onnx "$POCKET_ONNX")
  fi
  if [[ -n "$POCKET_CLASS_MAP" ]]; then
    pocket_extra+=(--pocket-class-map "$POCKET_CLASS_MAP")
  fi
  if [[ -n "$POCKET_MIN_CONF" ]]; then
    pocket_extra+=(--pocket-min-conf "$POCKET_MIN_CONF")
  fi
  pocket_extra+=(--rack-style "$RACK_STYLE")
  noff_extra=()
  if [[ "${CALIB_NO_FULLSCREEN:-}" == "1" ]]; then
    noff_extra+=(--no-fullscreen)
  fi
  overlay_arg=()
  if [[ -f "$CALIB_OVERLAY_JSON" ]]; then
    overlay_arg+=(--overlay-json "$CALIB_OVERLAY_JSON")
  fi
  exec "$(python_bin)" "$CALIB_SCRIPT" \
    "${overlay_arg[@]}" \
    "${noff_extra[@]}" \
    --camera "$CAMERA_SOURCE" \
    --csi-sensor-id "$CSI_SENSOR_ID" \
    --csi-framerate "$CSI_FRAMERATE" \
    --csi-open-retries "$CSI_OPEN_RETRIES" \
    --csi-flip-method "$CSI_FLIP_METHOD" \
    --width "$FRAME_WIDTH" \
    --height "$FRAME_HEIGHT" \
    --units "$UNITS" \
    --pocket-radius-m "$POCKET_RADIUS_M" \
    --out "$CALIB_OUT" \
    "${pocket_extra[@]}" \
    "$@"
}

main "$@"
