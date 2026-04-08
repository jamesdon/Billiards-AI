#!/usr/bin/env bash
set -euo pipefail

echo "Jetson Nano CSI camera setup/check"
echo "This script targets NVIDIA Jetson Nano (JetPack)."

echo
echo "[1/6] Verify project path"
PROJECT_ROOT="${PROJECT_ROOT:-/home/$USER/Billiards AI}"
if [[ ! -d "$PROJECT_ROOT" ]]; then
  echo "Project root not found: $PROJECT_ROOT" >&2
  exit 1
fi
echo "Project root: $PROJECT_ROOT"

echo
echo "[2/6] Install camera tooling (requires sudo)"
sudo apt-get update
sudo apt-get install -y v4l-utils gstreamer1.0-tools

echo
echo "[3/6] Restart Argus daemon"
sudo systemctl restart nvargus-daemon || true
sleep 2
sudo systemctl status nvargus-daemon --no-pager || true

echo
echo "[4/6] List camera/video devices"
v4l2-ctl --list-devices || true
ls -l /dev/video* || true

echo
echo "[5/6] Run CSI GStreamer smoke test (10 seconds)"
timeout 10s gst-launch-1.0 -e nvarguscamerasrc sensor-id=0 ! \
  "video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1" ! \
  nvvidconv ! "video/x-raw,format=I420" ! \
  fakesink || true

echo
echo "[6/6] Run app camera smoke test"
source "$PROJECT_ROOT/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --width 1280 --height 720 --mjpeg-port 8080 &
PID=$!
sleep 5
kill "$PID" || true
wait "$PID" || true

echo
echo "Jetson CSI setup/check complete."
echo "If failures occurred, re-check ribbon cable orientation, camera enablement, and JetPack camera stack."

