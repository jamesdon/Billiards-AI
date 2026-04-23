#!/usr/bin/env bash
# Orin / device: TEST_PLAN §1 via run_phase 1. For §3 (detection/tracking), run edge.main manually — see docs/3.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

export PROJECT_ROOT
export MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/model.onnx}"
export CLASS_MAP_PATH="${CLASS_MAP_PATH:-$PROJECT_ROOT/models/class_map.json}"

"$SCRIPT_DIR/run_phase.sh" 1
echo "jetson_phases_1.sh: OK (run edge.main for detection/tracking smoke per docs/3)"
