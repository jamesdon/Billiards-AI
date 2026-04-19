#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
PYTHON_BIN="$(python_bin)"
"$PYTHON_BIN" -m pip install -U pip
"$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt"

echo "[Phase1] Verifying OpenCV GStreamer support (required for CSI)..."
"$PYTHON_BIN" - <<'PY'
import cv2
info = cv2.getBuildInformation()
has_gst = any(("GStreamer" in ln and "YES" in ln.upper()) for ln in info.splitlines())
print("cv2:", cv2.__file__)
print("GStreamer:", "YES" if has_gst else "NO")
if not has_gst:
    raise SystemExit("OpenCV GStreamer support is required for CSI camera mode.")
PY

echo "[Phase1] Running integrity checks..."
run_with_timeout 180 "$PYTHON_BIN" -m compileall "$PROJECT_ROOT/core" "$PROJECT_ROOT/edge" "$PROJECT_ROOT/backend"
run_with_timeout 120 ruff check "$PROJECT_ROOT"
run_with_timeout 300 pytest -q "$PROJECT_ROOT/tests"

BACKEND_LOG="${PROJECT_ROOT}/.phase1_backend.log"
EDGE_LOG="${PROJECT_ROOT}/.phase1_edge.log"
BACKEND_PID=""
EDGE_PID=""

cleanup() {
  if [[ -n "${EDGE_PID}" ]] && kill -0 "${EDGE_PID}" 2>/dev/null; then
    kill "${EDGE_PID}" || true
    wait "${EDGE_PID}" || true
  fi
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" || true
    wait "${BACKEND_PID}" || true
  fi
}
trap cleanup EXIT

echo "[Phase1] Starting backend..."
run_with_timeout 1200 uvicorn backend.app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
BACKEND_PID="$!"

for _ in $(seq 1 30); do
  if /usr/bin/curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend failed to start. Log: $BACKEND_LOG" >&2
    exit 1
  fi
  sleep 1
done

HEALTH_JSON=$(/usr/bin/curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health")
STATE_JSON=$(/usr/bin/curl -fsS "http://127.0.0.1:${BACKEND_PORT}/live/state")
echo "[Phase1] /health => ${HEALTH_JSON}"
echo "[Phase1] /live/state => ${STATE_JSON}"

CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
MJPEG_PORT="${MJPEG_PORT:-8080}"
EDGE_TIMEOUT_SECONDS="${EDGE_TIMEOUT_SECONDS:-1200}"

echo "[Phase1] Starting edge CSI smoke test..."
run_with_timeout "${EDGE_TIMEOUT_SECONDS}" "$PYTHON_BIN" -m edge.main --camera csi --csi-sensor-id "${CSI_SENSOR_ID}" --csi-flip-method "${CSI_FLIP_METHOD}" --mjpeg-port "${MJPEG_PORT}" >"$EDGE_LOG" 2>&1 &
EDGE_PID="$!"

EDGE_READY=0
for _ in $(seq 1 45); do
  if /usr/bin/curl -fsS "http://127.0.0.1:${MJPEG_PORT}/mjpeg" >/dev/null 2>&1; then
    EDGE_READY=1
    break
  fi
  if ! kill -0 "$EDGE_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [[ "$EDGE_READY" -ne 1 ]]; then
  echo "Edge CSI smoke test failed. Log: $EDGE_LOG" >&2
  exit 1
fi

echo "[Phase1] MJPEG endpoint is reachable."
echo "[Phase1] Letting edge run for stability window..."
sleep 15

if ! kill -0 "$EDGE_PID" 2>/dev/null; then
  echo "Edge process exited unexpectedly during stability window. Log: $EDGE_LOG" >&2
  exit 1
fi

echo "[Phase1] PASS"

