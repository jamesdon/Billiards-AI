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
  echo "No runs found under $PROJECT_ROOT/runs/detect/*/weights/best.pt" >&2
  echo "" >&2
  echo "You need a trained checkpoint before this script can export to models/model.onnx. Pick one:" >&2
  echo "  A) Train on this device (needs labeled images under data/datasets/billiards/images/train/):" >&2
  echo "       bash \"$PROJECT_ROOT/scripts/jetson_yolo_train.sh\"" >&2
  echo "     Then re-run: bash \"$PROJECT_ROOT/scripts/jetson_yolo_export_latest.sh\"" >&2
  echo "  B) Copy a team-approved model.onnx from another machine (must match models/class_map.json):" >&2
  echo "       scp user@host:/path/to/model.onnx \"$PROJECT_ROOT/models/model.onnx\"" >&2
  echo "     See docs/MODEL_OPTIMIZATION.md (copy / scp) and docs/3 Detection and tracking.md." >&2
  echo "  C) If you already have best.pt elsewhere, copy it under runs/detect/<name>/weights/best.pt then re-run this script." >&2
  exit 1
fi
echo "Using: $LATEST_PT"
YOLO_CLI="$(yolo_bin)"
if [[ ! -x "$YOLO_CLI" ]]; then
  echo "Missing $YOLO_CLI — install training deps:" >&2
  echo "  $VENV_PATH/bin/python3 -m pip install -r \"$PROJECT_ROOT/requirements-train.txt\"" >&2
  exit 1
fi
"$YOLO_CLI" export model="$LATEST_PT" format=onnx imgsz="${YOLO_EXPORT_IMGSZ:-640}"
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
