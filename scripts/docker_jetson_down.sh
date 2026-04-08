#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/$USER/Billiards-AI}"
cd "$PROJECT_ROOT"

docker compose -f "$PROJECT_ROOT/docker-compose.jetson.yml" down
echo "Jetson stack stopped."

