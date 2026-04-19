#!/usr/bin/env bash
# Block 7: short edge.main smoke (CSI). Override CALIB_PATH if needed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
activate_venv
PYTHON_BIN="$(python_bin)"

CALIB_PATH="${CALIB_PATH:-$PROJECT_ROOT/calibration.json}"
MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/model.onnx}"
CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/models/class_map.json}"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
MJPEG_PORT="${MJPEG_PORT:-8080}"

require_file "$MODEL_PATH"
require_file "$CLASS_MAP_PATH"
require_file "$CALIB_PATH"

echo "Starting edge.main (CSI); press Ctrl+C to stop." >&2
"$PYTHON_BIN" -m edge.main \
  --camera csi \
  --csi-sensor-id "$CSI_SENSOR_ID" \
  --onnx-model "$MODEL_PATH" \
  --class-map "$CLASS_MAP_PATH" \
  --calib "$CALIB_PATH" \
  --detect-every-n 2 \
  --mjpeg-port "$MJPEG_PORT"
