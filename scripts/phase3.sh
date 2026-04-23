#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv

PYTHON_BIN="$(python_bin)"
"$PYTHON_BIN" -m pip install -U pip
"$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt"

MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/model.onnx}"
CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/models/class_map.json}"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
BASELINE_SECONDS="${BASELINE_SECONDS:-20}"
SWEEP_SECONDS="${SWEEP_SECONDS:-20}"
AUTO_WRITE_CLASS_MAP="${AUTO_WRITE_CLASS_MAP:-1}"

# Camera: CSI is for Jetson; macOS has no Argus CSI — default to USB unless overridden.
#   PHASE3_CAMERA=csi|usb|INDEX|gstreamer-string
#   PHASE3_USB_INDEX=0   (when PHASE3_CAMERA=usb)
PHASE3_CAMERA="${PHASE3_CAMERA:-}"
if [[ -z "${PHASE3_CAMERA}" ]]; then
  if [[ "$(/usr/bin/uname -s)" == "Darwin" ]]; then
    PHASE3_CAMERA=usb
  else
    PHASE3_CAMERA=csi
  fi
fi
PHASE3_USB_INDEX="${PHASE3_USB_INDEX:-0}"

phase3_build_cam_args() {
  local lcam
  lcam="$(printf '%s' "${PHASE3_CAMERA}" | tr '[:upper:]' '[:lower:]')"
  if [[ "$lcam" == "csi" ]]; then
    PHASE3_CAM_ARGS=(--camera csi --csi-sensor-id "${CSI_SENSOR_ID}" --csi-flip-method "${CSI_FLIP_METHOD}")
  elif [[ "$lcam" == "usb" ]]; then
    PHASE3_CAM_ARGS=(--camera usb --usb-index "${PHASE3_USB_INDEX}")
  elif [[ "${PHASE3_CAMERA}" =~ ^[0-9]+$ ]]; then
    PHASE3_CAM_ARGS=(--camera "${PHASE3_CAMERA}")
  else
    PHASE3_CAM_ARGS=(--camera "${PHASE3_CAMERA}")
  fi
}
phase3_build_cam_args

if [[ "$(/usr/bin/uname -s)" == "Darwin" ]] && [[ "$(printf '%s' "${PHASE3_CAMERA}" | tr '[:upper:]' '[:lower:]')" == "usb" ]]; then
  echo "[Phase3] macOS: allow Camera access (System Settings → Privacy & Security → Camera) for the app running this shell" >&2
  echo "[Phase3] (Terminal, iTerm, Cursor, etc.). 'not authorized to capture video' means that toggle is off for that app." >&2
fi
echo "[Phase3] Camera mode: ${PHASE3_CAMERA} (set PHASE3_CAMERA / PHASE3_USB_INDEX to override)" >&2
echo "[Phase3] Headless run: there is no OpenCV window. When each segment starts, open the printed http:// URL in a browser." >&2

if [[ ! -f "$CLASS_MAP_PATH" ]] && [[ "$AUTO_WRITE_CLASS_MAP" == "1" ]]; then
  mkdir -p "$(dirname "$CLASS_MAP_PATH")"
  cat > "$CLASS_MAP_PATH" <<'EOF'
{
  "0": "ball",
  "1": "person",
  "2": "cue_stick",
  "3": "rack"
}
EOF
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  cat >&2 <<EOF
Missing required file: $MODEL_PATH

Detection and tracking (see docs/3 …) requires a detector ONNX model. This repo does not ship model weights.

Typical new device: copy your shared team model (no training on device):
  cp "/path/to/released/model.onnx" "$PROJECT_ROOT/models/model.onnx"

Optional model refresh (train/tune once, reuse everywhere):
  1) Train/export per $PROJECT_ROOT/docs/MODEL_OPTIMIZATION.md, then place:
     $PROJECT_ROOT/models/model.onnx
  2) For pipeline smoke only (not accuracy validation), any local ONNX:
     cp "/path/to/some_model.onnx" "$PROJECT_ROOT/models/model.onnx"

See: $PROJECT_ROOT/docs/MODEL_OPTIMIZATION.md
EOF
  exit 1
fi
require_file "$CLASS_MAP_PATH"

# Fixed repo ports (docs/PORTS.md): 8001 baseline (n=2), 8004 (n=1), 8005 (n=3).
PHASE3_PORT_N2="${PHASE3_PORT_N2:-8001}"
PHASE3_PORT_N1="${PHASE3_PORT_N1:-8004}"
PHASE3_PORT_N3="${PHASE3_PORT_N3:-8005}"
for v in PHASE3_PORT_N2 PHASE3_PORT_N1 PHASE3_PORT_N3; do
  p="${!v}"
  if ! [[ "$p" =~ ^[0-9]+$ ]]; then
    echo "[Phase3] $v must be an integer (got: ${p})" >&2
    exit 1
  fi
  if (( p < 8001 || p > 8005 )); then
    echo "[Phase3] $v must be 8001-8005; 8000 is reserved for the API (see docs/PORTS.md)." >&2
    exit 1
  fi
done
echo "[Phase3] MJPEG sweep ports: ${PHASE3_PORT_N2} (n=2), ${PHASE3_PORT_N1} (n=1), ${PHASE3_PORT_N3} (n=3)" >&2

# This script spawns its own edge per segment. edge.main’s MJPEG server binds 0.0.0.0:port
# (see edge/overlay/stream_mjpeg.py). The preflight must use the same bind + SO_REUSEADDR as
# ThreadingMixin HTTPServer, or we can get false “in use” vs netstat, or false free vs real edge.
# Python: exit 0 = port free, 1 = EADDRINUSE (no stderr), 2 = other (message on stderr)
phase3_mjpeg_port_would_bind() {
  local p="$1" st
  if ! "$PYTHON_BIN" -c "import errno, socket, sys
p = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
  s.bind(('0.0.0.0', p))
  s.close()
except OSError as e:
  if e.errno == errno.EADDRINUSE:
    sys.exit(1)
  print('bind preflight: %s' % (e,), file=sys.stderr)
  sys.exit(2)
" "$p"; then
    st=$?
    if (( st == 1 )); then
      return 1
    fi
    echo "[Phase3] FATAL: unexpected bind preflight (exit $st) for 0.0.0.0:${p} (see message above if any)." >&2
    exit 1
  fi
  return 0
}

for v in PHASE3_PORT_N2 PHASE3_PORT_N1 PHASE3_PORT_N3; do
  pr="${!v}"
  if ! phase3_mjpeg_port_would_bind "$pr"; then
    echo "[Phase3] FATAL: TCP :${pr} (0.0.0.0) is already in use. This script must bind each port itself." >&2
    echo "[Phase3]        Stop the other process first. Common: a manual  edge.main  for smoke tests." >&2
    if command -v lsof >/dev/null 2>&1; then
      echo "[Phase3]        Listeners (if any) on this port:" >&2
      lsof -nP -iTCP:"$pr" -sTCP:LISTEN 2>/dev/null | sed 's/^/[Phase3]   /' >&2 || true
    else
      echo "[Phase3]        Find with:  lsof -nP -iTCP:${pr} -sTCP:LISTEN" >&2
    fi
    echo "[Phase3]        Or:  netstat -anv -p tcp 2>/dev/null | head -1;  netstat -anv -p tcp | grep \"\\.${pr} \"" >&2
    echo "[Phase3]        Or use other ports, e.g.  PHASE3_PORT_N2=8002 PHASE3_PORT_N1=8003 PHASE3_PORT_N3=8004  (see docs/PORTS.md)" >&2
    exit 1
  fi
done

EDGE_PID=""
cleanup() {
  if [[ -n "${EDGE_PID}" ]] && kill -0 "${EDGE_PID}" 2>/dev/null; then
    kill "${EDGE_PID}" || true
    wait "${EDGE_PID}" || true
  fi
}
trap cleanup EXIT

run_case() {
  local detect_n="$1"
  local port="$2"
  local seconds="$3"
  local log_file="$4"
  local label="$5"

  echo "[Phase3] Starting ${label} detect_every_n=${detect_n} port=${port}"
  # No `timeout`/`gtimeout` around `edge.main`: background `$!` must be the real
  # Python PID so `kill` + `trap` stop the listener. A `gtimeout` wrapper PID
  # can orphan `edge.main` (port 8001 etc. still bound). Each run is bounded by
  # `sleep` + `kill`+`wait` below.
  "$PYTHON_BIN" -m edge.main \
    "${PHASE3_CAM_ARGS[@]}" \
    --onnx-model "$MODEL_PATH" \
    --class-map "$CLASS_MAP_PATH" \
    --detect-every-n "${detect_n}" \
    --mjpeg-port "${port}" >"${log_file}" 2>&1 &
  EDGE_PID="$!"

  # No terminal output from edge while log is redirected — startup can be 30–90s+ (ONNX, cv2, camera).
  local max_wait="${PHASE3_MJPEG_WAIT_SECONDS:-90}"
  echo "[Phase3] Waiting for first /mjpeg on 127.0.0.1:${port} (not stuck: tail -f ${log_file}) — up to ${max_wait}s." >&2

  local ready=0
  local w=0
  while (( w < max_wait )); do
    w=$((w + 1))
    if /usr/bin/curl -fsS "http://127.0.0.1:${port}/mjpeg" --max-time 2 --output /dev/null >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$EDGE_PID" 2>/dev/null; then
      echo "[Phase3] Edge exited before MJPEG (see ${log_file})" >&2
      break
    fi
    if (( w % 10 == 0 )); then
      echo "[Phase3]   ... still waiting ${w}/${max_wait}s" >&2
    fi
    sleep 1
  done

  if [[ "$ready" -ne 1 ]]; then
    echo "[Phase3] ${label} failed to start stream within ${max_wait}s. Log: ${log_file}" >&2
    exit 1
  fi

  echo "[Phase3] Live MJPEG (open in browser for ~${seconds}s): http://127.0.0.1:${port}/mjpeg" >&2
  sleep "${seconds}"
  if ! kill -0 "$EDGE_PID" 2>/dev/null; then
    echo "[Phase3] ${label} exited unexpectedly. Log: ${log_file}" >&2
    exit 1
  fi

  kill "$EDGE_PID" || true
  wait "$EDGE_PID" || true
  EDGE_PID=""
  echo "[Phase3] ${label} PASS"
}

run_case 2 "${PHASE3_PORT_N2}" "${BASELINE_SECONDS}" "${PROJECT_ROOT}/.phase3_n2.log" "baseline"
run_case 1 "${PHASE3_PORT_N1}" "${SWEEP_SECONDS}" "${PROJECT_ROOT}/.phase3_n1.log" "sweep-n1"
run_case 3 "${PHASE3_PORT_N3}" "${SWEEP_SECONDS}" "${PROJECT_ROOT}/.phase3_n3.log" "sweep-n3"

echo "[Phase3] Automated checks PASS."
echo "[Phase3] Manual gate still required: confirm ID continuity/re-acquisition in live overlay."

