#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
MODEL_PATH="${MODEL_PATH:-}"
CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/class_map.json}"
IDENTITIES_PATH="${IDENTITIES_PATH:-$PROJECT_ROOT/identities.json}"
if [[ -z "$MODEL_PATH" ]]; then
  echo "Set MODEL_PATH to an ONNX model path." >&2
  exit 1
fi

python -m edge.main --camera "${CAMERA_SOURCE:-0}" --onnx-model "$MODEL_PATH" --class-map "$CLASS_MAP_PATH" --identities "$IDENTITIES_PATH"

