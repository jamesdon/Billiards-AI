#!/usr/bin/env bash
# Block 6: phase 1 and phase 3 (requires model + class map + camera where applicable).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

export PROJECT_ROOT
export MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/model.onnx}"
export CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/models/class_map.json}"

"$SCRIPT_DIR/run_phase.sh" 1
"$SCRIPT_DIR/run_phase.sh" 3
echo "jetson_phases_1_3.sh: OK"
