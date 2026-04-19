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

TRAIN_IMG_DIR="$PROJECT_ROOT/data/datasets/billiards/images/train"
train_n="$(find "$TRAIN_IMG_DIR" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) 2>/dev/null | wc -l | tr -d '[:space:]')"
if [[ "${train_n:-0}" -eq 0 ]]; then
  echo "ERROR: No training images under: $TRAIN_IMG_DIR" >&2
  echo "Create JPEGs/PNGs there (and val/ split) before training. Example:" >&2
  echo "  bash \"$PROJECT_ROOT/scripts/jetson_capture_training_frames.sh\" --count 300 --stride 20 --prefix session1" >&2
  echo "Then label/split into images/train and images/val per Ultralytics layout." >&2
  exit 1
fi

YOLO_CLI="$(yolo_bin)"
if [[ ! -x "$YOLO_CLI" ]]; then
  echo "Missing $YOLO_CLI — install training deps:" >&2
  echo "  $VENV_PATH/bin/python3 -m pip install -r \"$PROJECT_ROOT/requirements-train.txt\"" >&2
  exit 1
fi
"$YOLO_CLI" detect train \
  data="$DATA_YAML" \
  model="$YOLO_MODEL" \
  imgsz="$YOLO_IMGSZ" \
  epochs="$YOLO_EPOCHS" \
  batch="$YOLO_BATCH" \
  workers="$YOLO_WORKERS" \
  project="$PROJECT_ROOT/runs/detect"
echo "jetson_yolo_train.sh: OK"
