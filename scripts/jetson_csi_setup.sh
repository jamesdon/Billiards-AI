#!/usr/bin/env bash
set -euo pipefail

echo "Jetson-family CSI camera setup/check"
echo "Targets boards with nvarguscamerasrc (JetPack 5.x Orin Nano baseline; older Jetson Nano may differ)."

echo
echo "[1/6] Verify project path"
PROJECT_ROOT="${PROJECT_ROOT:-/home/$USER/Billiards-AI}"
if [[ ! -d "$PROJECT_ROOT" ]]; then
  echo "Project root not found: $PROJECT_ROOT" >&2
  exit 1
fi
echo "Project root: $PROJECT_ROOT"

echo
echo "[2/6] Install camera tooling (requires sudo)"
# Do not abort the whole script if a third-party apt repo (e.g. GitHub CLI) breaks `apt-get update`.
set +e
sudo apt-get -o Acquire::Retries=3 update
upd_rc=$?
set -e
if [[ "$upd_rc" -ne 0 ]]; then
  echo "WARNING: apt-get update exited $upd_rc (often a broken /etc/apt/sources.list.d entry)." >&2
  echo "  Fix or remove that source, then: sudo apt-get update && sudo apt-get install -y v4l-utils gstreamer1.0-tools" >&2
fi
sudo apt-get install -y v4l-utils gstreamer1.0-tools

echo
echo "[3/6] Restart Argus daemon"
sudo systemctl restart nvargus-daemon || true
sleep 2
sudo systemctl status nvargus-daemon --no-pager || true

echo
echo "[4/6] List camera/video devices"
v4l2-ctl --list-devices 2>&1 || true
echo "If v4l2-ctl also printed 'Cannot open device /dev/video0': that is normal when no USB UVC camera exists — ignore it for CSI."
ls -l /dev/video* 2>/dev/null || echo "(no /dev/video* nodes — normal for CSI-only; USB UVC cameras create /dev/video0, etc.)"
echo
echo "CSI uses Argus (nvarguscamerasrc), not /dev/video0. Seeing only /dev/media0 (tegra-camrtc) is expected on many Jetson images."

echo
echo "[4b/6] Media controller topology (entities = drivers + sensor pipeline)"
if command -v media-ctl >/dev/null 2>&1; then
  _top="$(media-ctl -d /dev/media0 -p 2>/dev/null || true)"
  echo "$_top"
  _entities="$(echo "$_top" | /usr/bin/grep '^entity ' 2>/dev/null | /usr/bin/wc -l | tr -d '[:space:]')"
  _entities="${_entities:-0}"
  if [[ "${_entities}" -lt 2 ]]; then
    echo "" >&2
    echo ">>> Few or no 'entity' lines: the kernel likely did NOT link a CSI sensor driver to this media device." >&2
    echo ">>> That matches Argus 'No cameras available'. Fix hardware (ribbon, port, module) or board config (jetson-io / device tree), then cold boot." >&2
  fi
else
  echo "(install v4l-utils for media-ctl: sudo apt-get install -y v4l-utils)"
fi

echo
echo "[5/6] Run CSI GStreamer smoke test (10 seconds)"
timeout 10s gst-launch-1.0 -e nvarguscamerasrc sensor-id=0 ! \
  "video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1" ! \
  nvvidconv ! "video/x-raw,format=I420" ! \
  fakesink || true

echo
echo "[6/6] Run app camera smoke test"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
# shellcheck source=common.sh
source "$PROJECT_ROOT/scripts/common.sh"
activate_venv
PYTHON_BIN="$(python_bin)"
"$PYTHON_BIN" -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method "$CSI_FLIP_METHOD" --width 1280 --height 720 --mjpeg-port 8001 &
PID=$!
sleep 5
kill "$PID" || true
wait "$PID" || true

echo
echo "Jetson CSI setup/check complete."
echo "csi-flip-method used: $CSI_FLIP_METHOD"
echo
echo "How to read results:"
echo "  • dmesg: use 'sudo dmesg' if plain dmesg says Operation not permitted."
echo "  • nvargus 'No cameras available': Argus does not enumerate a CSI sensor (ribbon, port, module, or daemon)."
echo "    Missing /dev/video0 alone is NOT proof the CSI stack is broken — try Argus anyway via step [5/6]."
echo "    Re-seat the CSI ribbon (correct orientation), try the other CSI port (sensor-id=1),"
echo "    confirm a supported camera module is installed, and check carrier docs / jetson-io."
echo "  • No 'imx' (or similar) lines in sudo dmesg after boot: kernel likely never probed a camera."
echo "  • media-ctl -d /dev/media0 -p with almost no 'entity' lines: same as above — no sensor graph."
echo "If failures occurred, re-check ribbon cable, camera module model vs carrier, and L4T/Argus stack."

