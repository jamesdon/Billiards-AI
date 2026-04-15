#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv

python -m pip install -U pip
python -m pip install -r "$PROJECT_ROOT/requirements.txt"

CALIB_PATH="${CALIB_PATH:-$PROJECT_ROOT/calibration.json}"
CALIB_INVALID_PATH="${CALIB_INVALID_PATH:-$PROJECT_ROOT/calibration_invalid.json}"
VALID_LOG="${PROJECT_ROOT}/.phase2_valid.log"
INVALID_LOG="${PROJECT_ROOT}/.phase2_invalid.log"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
MJPEG_PORT="${MJPEG_PORT:-8080}"
EDGE_TIMEOUT_SECONDS="${EDGE_TIMEOUT_SECONDS:-1200}"
PHASE2_REQUIRE_CAMERA="${PHASE2_REQUIRE_CAMERA:-1}"

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
python - "$CALIB_PATH" <<'PY'
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

if [[ "$PHASE2_REQUIRE_CAMERA" == "1" ]]; then
  echo "[Phase2] Running valid calibration edge startup smoke..."
  /usr/bin/timeout "${EDGE_TIMEOUT_SECONDS}" python -m edge.main --camera csi --csi-sensor-id "${CSI_SENSOR_ID}" --csi-flip-method "${CSI_FLIP_METHOD}" --calib "$CALIB_PATH" --mjpeg-port "${MJPEG_PORT}" >"$VALID_LOG" 2>&1 &
  EDGE_PID="$!"
  READY=0
  for _ in $(seq 1 45); do
    if /usr/bin/curl -fsS "http://127.0.0.1:${MJPEG_PORT}/mjpeg" --max-time 2 --output /dev/null >/dev/null 2>&1; then
      READY=1
      break
    fi
    if ! kill -0 "$EDGE_PID" 2>/dev/null; then
      break
    fi
    /usr/bin/sleep 1
  done
  if [[ "$READY" -ne 1 ]]; then
    echo "Valid calibration startup failed. Log: $VALID_LOG" >&2
    exit 1
  fi
  echo "[Phase2] Valid calibration loaded; MJPEG endpoint is reachable."
  kill "$EDGE_PID" || true
  wait "$EDGE_PID" || true
  EDGE_PID=""
else
  echo "[Phase2] Skipping camera smoke (PHASE2_REQUIRE_CAMERA=0)."
fi

echo "[Phase2] Building invalid calibration and verifying rejection..."
cp "$CALIB_PATH" "$CALIB_INVALID_PATH"
python - "$CALIB_INVALID_PATH" <<'PY'
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
/usr/bin/timeout 120 python -m edge.main --camera csi --csi-sensor-id "${CSI_SENSOR_ID}" --csi-flip-method "${CSI_FLIP_METHOD}" --calib "$CALIB_INVALID_PATH" --mjpeg-port "$((MJPEG_PORT + 1))" >"$INVALID_LOG" 2>&1
RC=$?
set -e
if [[ "$RC" -eq 0 ]]; then
  echo "Invalid calibration unexpectedly succeeded. Log: $INVALID_LOG" >&2
  exit 1
fi
if ! rg -q "top_middle_side|PocketLabel|ValueError" "$INVALID_LOG"; then
  echo "Invalid calibration failed, but did not show expected label/schema error. Log: $INVALID_LOG" >&2
  exit 1
fi

echo "[Phase2] PASS"

