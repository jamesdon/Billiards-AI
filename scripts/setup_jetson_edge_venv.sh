#!/usr/bin/env bash
# One-shot Jetson (Linux aarch64/arm64) edge venv: distro OpenCV + GStreamer for CSI.
# Run from repo root. Requires sudo once for apt. Do not use for macOS or x86_64.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

_m="$(/usr/bin/uname -m)"
_s="$(/usr/bin/uname -s)"
if [[ "$_s" != "Linux" ]] || [[ "$_m" != "aarch64" && "$_m" != "arm64" ]]; then
  echo "setup_jetson_edge_venv.sh: only for Linux aarch64/arm64 (this host: $_s $_m)." >&2
  exit 1
fi

echo "== Jetson edge venv: apt packages (sudo) =="
sudo /usr/bin/apt-get update
sudo /usr/bin/apt-get install -y python3-venv python3-pip python3-opencv python3-gst-1.0 gstreamer1.0-tools

cd_root

if ! /usr/bin/python3 -m venv -h >/dev/null 2>&1; then
  echo "If venv fails, install: sudo apt-get install -y python3.10-venv  # match /usr/bin/python3 --version" >&2
fi

echo "== Remove old venv; create venv with system site-packages =="
/usr/bin/rm -rf "$VENV_PATH"
/usr/bin/python3 -m venv --system-site-packages "$VENV_PATH"

# shellcheck disable=SC1090
source "$VENV_PATH/bin/activate"
export PYTHONNOUSERSITE=1

echo "== Pip: requirements only (never requirements-train.txt in this venv for CSI) =="
python -m pip install -U pip wheel
python -m pip install -r "$PROJECT_ROOT/requirements.txt"
python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless 2>/dev/null || true
/usr/bin/python3 -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless 2>/dev/null || true
for _cv in "$HOME"/.local/lib/python3.*/site-packages/cv2*; do
  if [[ -e "$_cv" ]]; then
    /usr/bin/rm -rf "$_cv"
  fi
done
python -m pip install --upgrade "numpy<2"

echo "== Verify OpenCV (must be distro path + GStreamer YES for CSI) =="
python - <<'PY'
import cv2
p = cv2.__file__.replace("\\", "/")
gs = "YES" if "GStreamer:                   YES" in cv2.getBuildInformation() else "NO"
print("cv2_path:", p)
print("GStreamer:", gs)
# Pip opencv-python lives under .venv/.../site-packages; distro cv2 is under /usr/.../dist-packages.
if ".venv" in p and "/dist-packages/" not in p:
    raise SystemExit("FAIL: cv2 is the pip wheel inside .venv. Uninstall pip opencv and use distro python3-opencv (re-run this script).")
if gs != "YES":
    raise SystemExit("FAIL: GStreamer is not YES. CSI will not work with this OpenCV build.")
print("setup_jetson_edge_venv.sh: OK")
PY
