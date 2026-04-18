#!/usr/bin/env bash
# Block 2: dataset dirs + billiards-data.yaml (absolute path).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
activate_venv
chmod +x "$PROJECT_ROOT/scripts/bootstrap_billiards_dataset.sh"
PROJECT_ROOT="$PROJECT_ROOT" "$PROJECT_ROOT/scripts/bootstrap_billiards_dataset.sh"
/usr/bin/grep '^path:' "$PROJECT_ROOT/data/datasets/billiards/billiards-data.yaml"
echo "jetson_prepare_yolo_dataset.sh: OK (verify path: line above is an absolute directory on this machine)"
