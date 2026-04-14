#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PROJECT_ROOT="${PROJECT_ROOT:-/home/$USER/Billiards-AI}"
CALIB_SCRIPT="${CALIB_SCRIPT:-$PROJECT_ROOT/scripts/calib_click.py}"
CALIB_OUT="${CALIB_OUT:-$PROJECT_ROOT/calibration.json}"

CAMERA_SOURCE="${CAMERA_SOURCE:-csi}"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-6}"
CSI_FRAMERATE="${CSI_FRAMERATE:-30}"
FRAME_WIDTH="${FRAME_WIDTH:-1280}"
FRAME_HEIGHT="${FRAME_HEIGHT:-720}"
UNITS="${UNITS:-imperial}"
POCKET_RADIUS_M="${POCKET_RADIUS_M:-0.07}"

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
  FRAME_WIDTH       (default: 1280)
  FRAME_HEIGHT      (default: 720)
  UNITS             (default: imperial)
  POCKET_RADIUS_M   (default: 0.07)

Example:
  /home/$USER/Billiards-AI/scripts/start_calibration.sh
EOF
}

assert_calibration_gui_features() {
  require_file "$CALIB_SCRIPT"
  /usr/bin/python3 - "$CALIB_SCRIPT" <<'PY'
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
text = target.read_text(encoding="utf-8", errors="ignore")
required_tokens = [
    "_rotate_step",
    "_nudge_pan_display",
    "Rot-",
    "Rot+",
    "Angle:",
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

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
    usage
    exit 0
  fi

  cd_root
  activate_venv
  assert_calibration_gui_features

  echo "Launching calibration GUI from: $CALIB_SCRIPT"
  echo "Output calibration path: $CALIB_OUT"
  exec python "$CALIB_SCRIPT" \
    --camera "$CAMERA_SOURCE" \
    --csi-sensor-id "$CSI_SENSOR_ID" \
    --csi-framerate "$CSI_FRAMERATE" \
    --csi-flip-method "$CSI_FLIP_METHOD" \
    --width "$FRAME_WIDTH" \
    --height "$FRAME_HEIGHT" \
    --units "$UNITS" \
    --pocket-radius-m "$POCKET_RADIUS_M" \
    --out "$CALIB_OUT"
}

main "$@"
