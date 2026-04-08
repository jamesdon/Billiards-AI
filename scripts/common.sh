#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/$USER/Billiards-AI}"
VENV_PATH="${VENV_PATH:-$PROJECT_ROOT/.venv}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

require_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "Missing required file: $p" >&2
    exit 1
  fi
}

activate_venv() {
  if [[ ! -d "$VENV_PATH" ]]; then
    python3 -m venv "$VENV_PATH"
  fi
  # shellcheck disable=SC1090
  source "$VENV_PATH/bin/activate"
}

cd_root() {
  cd "$PROJECT_ROOT"
}

