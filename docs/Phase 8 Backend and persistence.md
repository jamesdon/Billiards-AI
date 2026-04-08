# Phase 8: Backend and persistence

## Goal

Verify SQLite + Dynamo persistence paths.

## 1) Configure optional Dynamo tables

```bash
export AWS_REGION="us-east-1"
export BILLIARDS_DDB_PLAYER_TABLE="billiards_player_stats"
export BILLIARDS_DDB_STICK_TABLE="billiards_stick_stats"
```

## 2) Start backend

```bash
cd "/home/$USER/Billiards AI"
source "/home/$USER/Billiards AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## 3) Inject shot summary and game over

```bash
curl -s -X POST "http://127.0.0.1:8000/event" -H "Content-Type: application/json" -d '{"type":"shot_summary","ts":1710000200.0,"payload":{"shot_summary":{"shot_idx":1,"ts_start":1710000199.0,"ts_end":1710000200.0,"shooter_profile_id":"p1","stick_profile_id":"s1","tags":["break"],"cue_peak_speed_mps":3.1,"shooter_player_idx":0,"shooter_team_idx":0}}}'
curl -s -X POST "http://127.0.0.1:8000/event" -H "Content-Type: application/json" -d '{"type":"game_over","ts":1710000300.0,"payload":{"game_type":"9ball","play_mode":"singles","rulesets":{"9ball":"wpa"},"winner_team":0,"game_over_reason":"nine_ball_pocketed_legally","players":[{"name":"A","profile_id":"p1"}]}}'
```

## 4) Verify SQLite persistence

```bash
python - <<'PY'
import sqlite3
db="/home/$USER/Billiards AI/billiards.db"
con=sqlite3.connect(db)
print("events:", con.execute("select count(*) from events").fetchone()[0])
print("states:", con.execute("select count(*) from states").fetchone()[0])
PY
```

## 5) Verify Dynamo (if configured)

```bash
aws dynamodb query --table-name "$BILLIARDS_DDB_PLAYER_TABLE" --key-condition-expression "player_profile_id = :p" --expression-attribute-values '{":p":{"S":"p1"}}'
aws dynamodb query --table-name "$BILLIARDS_DDB_STICK_TABLE" --key-condition-expression "stick_profile_id = :s" --expression-attribute-values '{":s":{"S":"s1"}}'
```

## Pass criteria

- SQLite always stores events
- Dynamo stores player/stick/game records when configured

