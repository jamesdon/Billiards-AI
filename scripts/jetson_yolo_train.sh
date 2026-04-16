#!/usr/bin/env bash
# Block 3: Ultralytics train (edge-friendly defaults for Orin Nano; override with env vars).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
activate_venv

# Default name lets Ultralytics download weights into the project cwd if missing.
YOLO_MODEL="${YOLO_MODEL:-yolov8n.pt}"
YOLO_IMGSZ="${YOLO_IMGSZ:-640}"
YOLO_EPOCHS="${YOLO_EPOCHS:-30}"
YOLO_BATCH="${YOLO_BATCH:-4}"
YOLO_WORKERS="${YOLO_WORKERS:-2}"
DATA_YAML="$PROJECT_ROOT/data/datasets/billiards/billiards-data.yaml"

require_file "$DATA_YAML"
if [[ -f "$PROJECT_ROOT/$YOLO_MODEL" ]]; then
  YOLO_MODEL="$PROJECT_ROOT/$YOLO_MODEL"
fi

yolo detect train \
  data="$DATA_YAML" \
  model="$YOLO_MODEL" \
  imgsz="$YOLO_IMGSZ" \
  epochs="$YOLO_EPOCHS" \
  batch="$YOLO_BATCH" \
  workers="$YOLO_WORKERS" \
  project="$PROJECT_ROOT/runs/detect"
echo "jetson_yolo_train.sh: OK"
