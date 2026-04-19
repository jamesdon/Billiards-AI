#!/usr/bin/env bash
# Save live CSI frames into the dataset tree for later labeling (see docs/ORIN_NANO_TRAIN_AND_TEST.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
activate_venv
PYTHON_BIN="$(python_bin)"

exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/capture_csi_training_frames.py" "$@"
