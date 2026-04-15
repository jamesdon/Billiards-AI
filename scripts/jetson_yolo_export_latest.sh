#!/usr/bin/env bash
# Block 4: export newest runs/detect/*/weights/best.pt to models/model.onnx
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
activate_venv

LATEST_PT="$(ls -t "$PROJECT_ROOT/runs/detect/"*/weights/best.pt 2>/dev/null | head -1 || true)"
if [[ -z "${LATEST_PT}" ]]; then
  echo "No runs found under $PROJECT_ROOT/runs/detect/*/weights/best.pt — train first (jetson_yolo_train.sh)." >&2
  exit 1
fi
echo "Using: $LATEST_PT"
yolo export model="$LATEST_PT" format=onnx imgsz="${YOLO_EXPORT_IMGSZ:-640}"
WEIGHTS_DIR="$(dirname "$LATEST_PT")"
ONNX_OUT="$WEIGHTS_DIR/best.onnx"
if [[ ! -f "$ONNX_OUT" ]]; then
  echo "Missing $ONNX_OUT after export" >&2
  exit 1
fi
mkdir -p "$PROJECT_ROOT/models"
cp "$ONNX_OUT" "$PROJECT_ROOT/models/model.onnx"
ls -lh "$PROJECT_ROOT/models/model.onnx" "$PROJECT_ROOT/models/class_map.json"
echo "jetson_yolo_export_latest.sh: OK"
