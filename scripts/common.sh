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
    if [[ "$(/usr/bin/uname -m)" == "aarch64" ]]; then
      # Jetson CSI requires distro OpenCV with GStreamer support.
      python3 -m venv --system-site-packages "$VENV_PATH"
    else
      python3 -m venv "$VENV_PATH"
    fi
  fi
  # shellcheck disable=SC1090
  source "$VENV_PATH/bin/activate"
  # Ensure user-site Python packages (e.g. ~/.local) do not override Jetson
  # distro OpenCV with a non-GStreamer pip build.
  export PYTHONNOUSERSITE=1
}

cd_root() {
  cd "$PROJECT_ROOT"
}

