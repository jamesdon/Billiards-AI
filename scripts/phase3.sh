#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
MODEL_PATH="${MODEL_PATH:-}"
CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/class_map.json}"
if [[ -z "$MODEL_PATH" ]]; then
  echo "Set MODEL_PATH to an ONNX model path." >&2
  exit 1
fi
require_file "$MODEL_PATH"
require_file "$CLASS_MAP_PATH"

python -m edge.main --camera "${CAMERA_SOURCE:-0}" --onnx-model "$MODEL_PATH" --class-map "$CLASS_MAP_PATH" --detect-every-n "${DETECT_EVERY_N:-2}" --mjpeg-port "${MJPEG_PORT:-8080}"

