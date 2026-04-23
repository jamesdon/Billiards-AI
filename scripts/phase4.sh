#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
PYTHON_BIN="$(python_bin)"
MODEL_PATH="${MODEL_PATH:-}"
CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/models/class_map.json}"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
if [[ -z "$MODEL_PATH" ]]; then
  echo "Set MODEL_PATH to an ONNX model path." >&2
  exit 1
fi

"$PYTHON_BIN" -m edge.main \
  --camera "${CAMERA_SOURCE:-csi}" \
  --csi-sensor-id "${CSI_SENSOR_ID}" \
  --csi-flip-method "${CSI_FLIP_METHOD}" \
  --onnx-model "$MODEL_PATH" \
  --class-map "$CLASS_MAP_PATH" \
  --identities "$PROJECT_ROOT/identities.json"

