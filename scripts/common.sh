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

ensure_numpy_cv2_compat() {
  local py_bin="python"
  if ! command -v "$py_bin" >/dev/null 2>&1; then
    py_bin="python3"
  fi

  # Detect Jetson/OpenCV ABI mismatch: cv2 built against NumPy 1.x while
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

