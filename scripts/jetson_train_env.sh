#!/usr/bin/env bash
# Block 1: git pull, venv, pip install (edge + YOLO training deps).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
git pull
test -d "$PROJECT_ROOT/.venv" || python3 -m venv --system-site-packages "$PROJECT_ROOT/.venv"
activate_venv
python -m pip install -U pip
python -m pip install -r "$PROJECT_ROOT/requirements.txt"
python -m pip install -r "$PROJECT_ROOT/requirements-train.txt"
echo "jetson_train_env.sh: OK"
