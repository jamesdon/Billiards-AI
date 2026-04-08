#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
python -m pip install -U pip
python -m pip install -r "$PROJECT_ROOT/requirements.txt"
python -m compileall "$PROJECT_ROOT/core" "$PROJECT_ROOT/edge" "$PROJECT_ROOT/backend"
ruff check "$PROJECT_ROOT"
pytest -q "$PROJECT_ROOT/tests"

echo "Phase 1 complete."

