# Phase 7: Stats and analytics

## Goal

Validate shot summaries and derived analytics fields.

## 1) Start backend

```bash
cd "/home/$USER/Billiards AI"
source "/home/$USER/Billiards AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## 2) Inject representative shot summary

```bash
curl -s -X POST "http://127.0.0.1:8000/event" \
  -H "Content-Type: application/json" \
  -d '{
    "type":"shot_summary",
    "ts":1710000100.0,
    "payload":{
      "shot_summary":{
        "shot_idx":12,
        "ts_start":1710000099.2,
        "ts_end":1710000100.0,
        "shooter_player_idx":0,
        "shooter_team_idx":0,
        "cue_peak_speed_mps":2.8,
        "shooter_profile_id":"p1",
        "stick_profile_id":"s1",
        "tags":["follow","cut"],
        "follow_distance_m":0.42,
        "draw_distance_m":0.0,
        "cut_angle_deg":26.0,
        "break_rail_hits":0,
        "break_pocketed":[],
        "rail_hits_by_ball":{"3":1}
      }
    }
  }'
```

## 3) Verify stored event contains expected fields

```bash
python - <<'PY'
import sqlite3, json
db="/home/$USER/Billiards AI/billiards.db"
con=sqlite3.connect(db)
row=con.execute("select payload from events where json_extract(payload, '$.type')='shot_summary' order by id desc limit 1").fetchone()
print(json.dumps(json.loads(row[0]), indent=2))
PY
```

## Pass criteria

- shot summary fields present and numerically sane

