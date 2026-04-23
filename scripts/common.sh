#!/usr/bin/env bash
set -euo pipefail

# Default repo root: parent of this file's directory (works on laptop + Jetson).
# Override with PROJECT_ROOT=/path/to/Billiards-AI when needed.
_common_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_default_root="$(cd "$_common_dir/.." && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$_default_root}"
unset _common_dir _default_root
VENV_PATH="${VENV_PATH:-$PROJECT_ROOT/.venv}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8780}"

require_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "Missing required file: $p" >&2
    exit 1
  fi
}

# Ultralytics CLI: always invoke via absolute path (some shells leave `yolo` off PATH after `activate`).
yolo_bin() {
  echo "${VENV_PATH}/bin/yolo"
}

# Repo venv interpreter: use `python3` explicitly. Some venvs omit a `python` shim; pyenv then
# intercepts `python` and fails with "command not found".
python_bin() {
  if [[ -x "${VENV_PATH}/bin/python3" ]]; then
    echo "${VENV_PATH}/bin/python3"
  elif [[ -x "${VENV_PATH}/bin/python" ]]; then
    echo "${VENV_PATH}/bin/python"
  else
    echo "python3"
  fi
}

activate_venv() {
  if [[ ! -d "$VENV_PATH" ]]; then
    if [[ "$(/usr/bin/uname -m)" == "aarch64" ]]; then
      # NVIDIA CSI on Jetson requires distro OpenCV with GStreamer support.
      python3 -m venv --system-site-packages "$VENV_PATH"
    else
      python3 -m venv "$VENV_PATH"
    fi
  fi
  # shellcheck disable=SC1090
  source "$VENV_PATH/bin/activate"
  # Ensure user-site Python packages (e.g. ~/.local) do not override distro
  # OpenCV with a non-GStreamer pip build.
  export PYTHONNOUSERSITE=1
}

ensure_numpy_cv2_compat() {
  local py_bin
  py_bin="$(python_bin)"
  if ! command -v "$py_bin" >/dev/null 2>&1; then
    py_bin="python3"
  fi

  # Detect OpenCV/NumPy ABI mismatch: cv2 built against NumPy 1.x while
  # environment has NumPy 2.x.
  set +e
  "$py_bin" - <<'PY'
import sys

try:
    import cv2  # noqa: F401
except Exception as exc:  # pragma: no cover - shell helper probe
    msg = str(exc)
    if (
        "_ARRAY_API not found" in msg
        or "numpy.core.multiarray failed to import" in msg
        or "compiled using NumPy 1.x cannot be run in NumPy 2" in msg
    ):
        raise SystemExit(42)
    raise SystemExit(43)

raise SystemExit(0)
PY
  local probe_rc=$?
  set -e

  if [[ "$probe_rc" -eq 0 ]]; then
    return 0
  fi

  if [[ "$probe_rc" -eq 42 ]]; then
    echo "Detected OpenCV/NumPy ABI mismatch. Repairing with numpy<2..." >&2
    "$py_bin" -m pip install --upgrade --force-reinstall "numpy<2"
    "$py_bin" - <<'PY'
import cv2  # noqa: F401
print("OpenCV/NumPy compatibility check: OK")
PY
    return 0
  fi

  echo "Python/OpenCV import check failed for an unexpected reason." >&2
  return 1
}

cd_root() {
  cd "$PROJECT_ROOT"
}

# GNU `timeout` is often missing on macOS; Homebrew coreutils provides `gtimeout`.
run_with_timeout() {
  local max_secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "${max_secs}" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "${max_secs}" "$@"
  elif [[ -x /usr/bin/timeout ]]; then
    /usr/bin/timeout "${max_secs}" "$@"
  else
    "$@"
  fi
}

