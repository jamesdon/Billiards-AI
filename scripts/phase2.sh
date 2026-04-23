#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
PYTHON_BIN="$(python_bin)"

echo "[Phase2] Headless validation only (no GUI). For interactive calibration run:" >&2
echo "       bash \"$PROJECT_ROOT/scripts/start_calibration.sh\"" >&2
echo "[Phase2] (Requires a desktop session on the Orin Nano, or X11 forwarding.)" >&2

"$PYTHON_BIN" -m pip install -U pip
"$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt"

CALIB_PATH="${CALIB_PATH:-$PROJECT_ROOT/calibration.json}"
CALIB_INVALID_PATH="${CALIB_INVALID_PATH:-$PROJECT_ROOT/calibration_invalid.json}"
VALID_LOG="${PROJECT_ROOT}/.phase2_valid.log"
INVALID_LOG="${PROJECT_ROOT}/.phase2_invalid.log"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
EDGE_TIMEOUT_SECONDS="${EDGE_TIMEOUT_SECONDS:-1200}"
PHASE2_REQUIRE_CAMERA="${PHASE2_REQUIRE_CAMERA:-1}"
# Camera for edge.main smoke. Invalid-label run fails at Calibration.load before capture but uses
# the same camera args for consistency.
# Unset: Darwin → usb (no Jetson CSI), Linux/Jetson → csi. Override: PHASE2_CAMERA=usb|0|gstreamer string.
PHASE2_CAMERA="${PHASE2_CAMERA:-}"
if [[ -z "${PHASE2_CAMERA}" ]]; then
  if [[ "$(/usr/bin/uname -s)" == "Darwin" ]]; then
    PHASE2_CAMERA=usb
  else
    PHASE2_CAMERA=csi
  fi
fi
PHASE2_USB_INDEX="${PHASE2_USB_INDEX:-0}"

phase2_build_cam_args() {
  local lcam
  lcam="$(printf '%s' "${PHASE2_CAMERA}" | tr '[:upper:]' '[:lower:]')"
  if [[ "$lcam" == "csi" ]]; then
    PHASE2_CAM_ARGS=(--camera csi --csi-sensor-id "${CSI_SENSOR_ID}" --csi-flip-method "${CSI_FLIP_METHOD}")
  elif [[ "$lcam" == "usb" ]]; then
    PHASE2_CAM_ARGS=(--camera usb --usb-index "${PHASE2_USB_INDEX}")
  elif [[ "${PHASE2_CAMERA}" =~ ^[0-9]+$ ]]; then
    PHASE2_CAM_ARGS=(--camera "${PHASE2_CAMERA}")
  else
    PHASE2_CAM_ARGS=(--camera "${PHASE2_CAMERA}")
  fi
}

phase2_build_cam_args

# Avoid colliding with a long-running edge (or anything else) on 8080: pick a free
# localhost port unless MJPEG_PORT is set explicitly (even to 8080).
if [[ -z "${MJPEG_PORT:-}" ]]; then
  MJPEG_PORT="$(
    "$PYTHON_BIN" - <<'PY'
import socket
for p in range(18080, 18256):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", p))
    except OSError:
        continue
    finally:
        s.close()
    print(p)
    break
else:
    raise SystemExit("no free TCP port in 18080-18255 for phase2 MJPEG smoke")
PY
  )"
  echo "[Phase2] Auto-selected MJPEG_PORT=${MJPEG_PORT} (export MJPEG_PORT=8080 to pin a port)." >&2
else
  echo "[Phase2] Using MJPEG_PORT=${MJPEG_PORT} from environment." >&2
fi

# GNU coreutils timeout is not on all macOS installs; fall back to no timeout.
run_with_timeout() {
  local max_secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "${max_secs}" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "${max_secs}" "$@"
  elif [ -x /usr/bin/timeout ]; then
    /usr/bin/timeout "${max_secs}" "$@"
  else
    "$@"
  fi
}

echo "[Phase2] Writing baseline calibration file: $CALIB_PATH"
cat > "$CALIB_PATH" <<'EOF'
{
  "H": [[1,0,0],[0,1,0],[0,0,1]],
  "pockets": [
    {"label":"top_left_corner","center_xy_m":[0.0,0.0],"radius_m":0.07},
    {"label":"top_right_corner","center_xy_m":[0.0,1.42],"radius_m":0.07},
    {"label":"bottom_left_corner","center_xy_m":[2.84,0.0],"radius_m":0.07},
    {"label":"bottom_right_corner","center_xy_m":[2.84,1.42],"radius_m":0.07},
    {"label":"left_side_pocket","center_xy_m":[1.42,0.0],"radius_m":0.07},
    {"label":"right_side_pocket","center_xy_m":[1.42,1.42],"radius_m":0.07}
  ]
}
EOF

echo "[Phase2] Validating calibration schema and pocket labels..."
"$PYTHON_BIN" - "$CALIB_PATH" <<'PY'
import json
import sys
from core.types import PocketLabel
from edge.calib.calib_store import Calibration

path = sys.argv[1]
cal = Calibration.load(path)
expected = {e.value for e in PocketLabel}
actual = {p.label.value for p in cal.pockets}
missing = expected - actual
extra = actual - expected
if missing or extra:
    raise SystemExit(f"Pocket label mismatch. missing={sorted(missing)} extra={sorted(extra)}")
print(f"calibration_ok pockets={len(cal.pockets)}")

with open(path, "r", encoding="utf-8") as f:
    d = json.load(f)
print("homography_rows=", len(d.get("H", [])))
PY

EDGE_PID=""
cleanup() {
  if [[ -n "${EDGE_PID}" ]] && kill -0 "${EDGE_PID}" 2>/dev/null; then
    kill "${EDGE_PID}" || true
    wait "${EDGE_PID}" || true
  fi
}
trap cleanup EXIT

phase2_hint_valid_log() {
  local log="$1"
  [[ -f "$log" ]] || return 0
  if grep -qE "Address already in use|Errno 98" "$log" 2>/dev/null; then
    echo "[Phase2] Hint: MJPEG port is in use. Pin a free port: MJPEG_PORT=18081 bash scripts/phase2.sh" >&2
  fi
  if grep -qE "No cameras available" "$log" 2>/dev/null; then
    echo "[Phase2] Hint: Argus reports no CSI sensors (ribbon, wrong CSI port, or unsupported module)." >&2
    echo "[Phase2]       Run: bash \"$PROJECT_ROOT/scripts/jetson_csi_setup.sh\"  try CSI_SENSOR_ID=1  cold boot." >&2
    echo "[Phase2]       Partial Phase 2 without CSI: PHASE2_CAMERA=usb bash \"$PROJECT_ROOT/scripts/phase2.sh\" (or PHASE2_CAMERA=0)." >&2
  fi
  if grep -qE "CaptureSession|nvarguscamerasrc|Failed to open camera|no frames" "$log" 2>/dev/null; then
    echo "[Phase2] Hint: CSI/Argus camera did not produce frames. Stop other camera apps, try --csi-flip-method 0 or 6," >&2
    echo "[Phase2]       confirm sensor-id, and see docs/Phase 2 Calibration and coordinate mapping.md (Troubleshooting)." >&2
  fi
  if grep -qE "GStreamer=NO|without GStreamer|CSI camera mode requires OpenCV with GStreamer" "$log" 2>/dev/null; then
    echo "[Phase2] Hint: --camera csi needs OpenCV with GStreamer (Jetson: distro python3-opencv + venv --system-site-packages). On macOS use USB (default when PHASE2_CAMERA is unset) or PHASE2_CAMERA=0." >&2
  fi
}

if [[ "$PHASE2_REQUIRE_CAMERA" == "1" ]]; then
  echo "[Phase2] Running valid calibration edge startup smoke (camera=${PHASE2_CAMERA})..."
  echo "[Phase2] Note: /mjpeg never ends; we probe /health first, then one bounded /mjpeg download."
  PYTHONUNBUFFERED=1 run_with_timeout "${EDGE_TIMEOUT_SECONDS}" "$PYTHON_BIN" -u -m edge.main \
    "${PHASE2_CAM_ARGS[@]}" --calib "$CALIB_PATH" --mjpeg-port "${MJPEG_PORT}" >"$VALID_LOG" 2>&1 &
  EDGE_PID="$!"
  echo "[Phase2] Waiting for MJPEG TCP on 127.0.0.1:${MJPEG_PORT} (first import can be slow on device)..." >&2
  TCP_READY=0
  for i in $(seq 1 300); do
    if ! kill -0 "$EDGE_PID" 2>/dev/null; then
      echo "[Phase2] edge exited before MJPEG listened (attempt ${i}). Log: $VALID_LOG" >&2
      echo "Valid calibration startup failed (MJPEG port never opened). Log: $VALID_LOG" >&2
      phase2_hint_valid_log "$VALID_LOG"
      exit 1
    fi
    if "$PYTHON_BIN" -c "import socket; s=socket.socket(); s.settimeout(0.4); s.connect(('127.0.0.1',${MJPEG_PORT})); s.close()" 2>/dev/null; then
      TCP_READY=1
      break
    fi
    if (( i % 25 == 0 )); then
      echo "[Phase2] still waiting for TCP ${MJPEG_PORT} ... (${i}/300, ~$((i / 5))s wall)" >&2
    fi
    sleep 0.2
  done
  if [[ "$TCP_READY" -ne 1 ]]; then
    echo "Valid calibration startup failed (MJPEG port never accepted TCP within ~60s). Log: $VALID_LOG" >&2
    phase2_hint_valid_log "$VALID_LOG"
    exit 1
  fi
  READY=0
  for i in $(seq 1 30); do
    if /usr/bin/curl -fsS "http://127.0.0.1:${MJPEG_PORT}/health" --max-time 2 -o /dev/null 2>/dev/null; then
      READY=1
      break
    fi
    if ! kill -0 "$EDGE_PID" 2>/dev/null; then
      echo "[Phase2] edge exited before /health responded (attempt ${i}). Log: $VALID_LOG" >&2
      phase2_hint_valid_log "$VALID_LOG"
      break
    fi
    sleep 0.2
  done
  if [[ "$READY" -ne 1 ]]; then
    echo "Valid calibration startup failed (TCP open but /health not OK). Log: $VALID_LOG" >&2
    phase2_hint_valid_log "$VALID_LOG"
    exit 1
  fi
  MJPEG_PROBE="${PROJECT_ROOT}/.phase2_mjpeg_probe.bin"
  rm -f "$MJPEG_PROBE"
  echo "[Phase2] Probing first MJPEG bytes (max 25s; needs live camera frames)..." >&2
  set +e
  /usr/bin/curl -sS "http://127.0.0.1:${MJPEG_PORT}/mjpeg" --max-time 25 -o "$MJPEG_PROBE" 2>/dev/null
  _mjpeg_rc=$?
  set -e
  _mjpeg_sz=0
  if [[ -f "$MJPEG_PROBE" ]]; then
    _mjpeg_sz=$(/usr/bin/wc -c <"$MJPEG_PROBE" | tr -d ' ')
  fi
  rm -f "$MJPEG_PROBE"
  if [[ "${_mjpeg_sz:-0}" -lt 400 ]]; then
    echo "[Phase2] MJPEG stream too small (${_mjpeg_sz} bytes, curl rc=${_mjpeg_rc}); camera may not be producing frames. Log: $VALID_LOG" >&2
    exit 1
  fi
  echo "[Phase2] Valid calibration loaded; /health OK and MJPEG stream returned data."
  kill "$EDGE_PID" || true
  wait "$EDGE_PID" || true
  EDGE_PID=""
else
  echo "[Phase2] Skipping camera smoke (PHASE2_REQUIRE_CAMERA=0)."
fi

echo "[Phase2] Building invalid calibration and verifying rejection..."
cp "$CALIB_PATH" "$CALIB_INVALID_PATH"
"$PYTHON_BIN" - "$CALIB_INVALID_PATH" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    d = json.load(f)
d["pockets"][0]["label"] = "top_middle_side"
with open(path, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2)
print("written", path)
PY

set +e
run_with_timeout 120 "$PYTHON_BIN" -m edge.main \
  "${PHASE2_CAM_ARGS[@]}" --calib "$CALIB_INVALID_PATH" --mjpeg-port "$((MJPEG_PORT + 1))" >"$INVALID_LOG" 2>&1
RC=$?
set -e
if [[ "$RC" -eq 0 ]]; then
  echo "Invalid calibration unexpectedly succeeded. Log: $INVALID_LOG" >&2
  exit 1
fi
if ! grep -qE "top_middle_side|PocketLabel|ValueError" "$INVALID_LOG"; then
  echo "Invalid calibration failed, but did not show expected label/schema error. Log: $INVALID_LOG" >&2
  exit 1
fi

echo "[Phase2] PASS"
echo "[Phase2] No GUI was used. To open the calibration window: bash \"$PROJECT_ROOT/scripts/start_calibration.sh\"" >&2

