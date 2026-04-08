#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv

curl -s -X POST "http://127.0.0.1:${BACKEND_PORT}/event" \
  -H "Content-Type: application/json" \
  -d '{"type":"shot_summary","ts":1710000100.0,"payload":{"shot_summary":{"shot_idx":12,"ts_start":1710000099.2,"ts_end":1710000100.0,"shooter_player_idx":0,"shooter_team_idx":0,"cue_peak_speed_mps":2.8,"shooter_profile_id":"p1","stick_profile_id":"s1","tags":["follow","cut"],"follow_distance_m":0.42,"draw_distance_m":0.0,"cut_angle_deg":26.0}}}'

python - <<'PY'
import sqlite3, os
db=os.path.join("/Home", os.environ.get("USER",""), "Billiards AI", "billiards.db")
con=sqlite3.connect(db)
print(con.execute("select count(*) from events").fetchone()[0])
PY

echo "Phase 7 complete."

