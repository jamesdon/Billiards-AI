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
MJPEG_PORT="${MJPEG_PORT:-8080}"
EDGE_TIMEOUT_SECONDS="${EDGE_TIMEOUT_SECONDS:-1200}"
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

Phase 3 requires a detector ONNX model. This repo does not ship model weights.

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
  run_with_timeout "${EDGE_TIMEOUT_SECONDS}" "$PYTHON_BIN" -m edge.main \
    "${PHASE3_CAM_ARGS[@]}" \
    --onnx-model "$MODEL_PATH" \
    --class-map "$CLASS_MAP_PATH" \
    --detect-every-n "${detect_n}" \
    --mjpeg-port "${port}" >"${log_file}" 2>&1 &
  EDGE_PID="$!"

  local ready=0
  for _ in $(seq 1 45); do
    if /usr/bin/curl -fsS "http://127.0.0.1:${port}/mjpeg" --max-time 2 --output /dev/null >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$EDGE_PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done

  if [[ "$ready" -ne 1 ]]; then
    echo "[Phase3] ${label} failed to start stream. Log: ${log_file}" >&2
    exit 1
  fi

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

run_case 2 "${MJPEG_PORT}" "${BASELINE_SECONDS}" "${PROJECT_ROOT}/.phase3_n2.log" "baseline"
run_case 1 "$((MJPEG_PORT + 2))" "${SWEEP_SECONDS}" "${PROJECT_ROOT}/.phase3_n1.log" "sweep-n1"
run_case 3 "$((MJPEG_PORT + 3))" "${SWEEP_SECONDS}" "${PROJECT_ROOT}/.phase3_n3.log" "sweep-n3"

echo "[Phase3] Automated checks PASS."
echo "[Phase3] Manual gate still required: confirm ID continuity/re-acquisition in live overlay."

