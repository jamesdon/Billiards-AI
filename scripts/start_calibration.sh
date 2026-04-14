#!/usr/bin/env bash
set -euo pipefail

cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1

exec python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id "${CSI_SENSOR_ID:-0}" \
  --csi-framerate "${CSI_FRAMERATE:-30}" \
  --csi-flip-method "${CSI_FLIP_METHOD:-6}" \
  --width "${FRAME_WIDTH:-1280}" \
  --height "${FRAME_HEIGHT:-720}" \
  --units "${UNITS:-imperial}" \
  --pocket-radius-m "${POCKET_RADIUS_M:-0.07}" \
  --out "${CALIB_OUT:-/home/$USER/Billiards-AI/calibration.json}"
