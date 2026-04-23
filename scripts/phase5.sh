#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv

curl -s -X POST "http://127.0.0.1:${BACKEND_PORT}/fouls/manual" \
  -H "Content-Type: application/json" \
  -d '{"game_type":"8ball","foul_type":"touched_ball","player_idx":0,"team_idx":0,"notes":"phase5 test foul"}'

curl -s "http://127.0.0.1:${BACKEND_PORT}/live/state"
echo
echo "Step 5 checks complete."

