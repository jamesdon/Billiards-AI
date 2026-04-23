#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/$USER/Billiards-AI}"
cd "$PROJECT_ROOT"

mkdir -p "$PROJECT_ROOT/data" "$PROJECT_ROOT/models"
if [[ ! -f "$PROJECT_ROOT/identities.json" ]]; then
  echo '{"players":[],"sticks":[]}' > "$PROJECT_ROOT/identities.json"
fi

docker compose -f "$PROJECT_ROOT/docker-compose.jetson.yml" up -d
docker compose -f "$PROJECT_ROOT/docker-compose.jetson.yml" ps

echo "Jetson stack started."
echo "Backend: http://127.0.0.1:8000/health"
echo "MJPEG:   http://127.0.0.1:8001/mjpeg"

