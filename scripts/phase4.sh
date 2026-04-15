#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
MODEL_PATH="${MODEL_PATH:-}"
CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/class_map.json}"
IDENTITIES_PATH="${IDENTITIES_PATH:-$PROJECT_ROOT/identities.json}"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
if [[ -z "$MODEL_PATH" ]]; then
  echo "Set MODEL_PATH to an ONNX model path." >&2
  exit 1
fi

python -m edge.main \
  --camera "${CAMERA_SOURCE:-csi}" \
  --csi-sensor-id "${CSI_SENSOR_ID}" \
  --csi-flip-method "${CSI_FLIP_METHOD}" \
  --onnx-model "$MODEL_PATH" \
  --class-map "$CLASS_MAP_PATH" \
  --identities "$IDENTITIES_PATH"

