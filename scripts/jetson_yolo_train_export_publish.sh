#!/usr/bin/env bash
# Train → export newest best.pt to models/model.onnx → git commit (optional push).
# Training deps: requirements-train.txt. Set GIT_PUSH=1 to push after commit.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root

bash "$SCRIPT_DIR/jetson_yolo_train.sh"
bash "$SCRIPT_DIR/jetson_yolo_export_latest.sh"
# Re-use GIT_PUSH / MODEL_COMMIT_MSG from the environment for publish_trained_model.sh
bash "$SCRIPT_DIR/publish_trained_model.sh"
echo "jetson_yolo_train_export_publish.sh: OK"
