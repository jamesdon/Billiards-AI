#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
require_file "$PROJECT_ROOT/calibration.json"

python -m edge.main --camera "${CAMERA_SOURCE:-0}" --calib "$PROJECT_ROOT/calibration.json" --mjpeg-port "${MJPEG_PORT:-8080}"

