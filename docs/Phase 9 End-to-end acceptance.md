# Phase 9: End-to-end acceptance

## Goal

Run a full real-world match and validate output correctness.

## 1) Start backend

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## 2) Start edge with full config

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main \
  --camera csi \
  --csi-sensor-id 0 \
  --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" \
  --class-map "/home/$USER/Billiards-AI/class_map.json" \
  --calib "/home/$USER/Billiards-AI/calibration.json" \
  --identities "/home/$USER/Billiards-AI/identities.json" \
  --players "Player A,Player B" \
  --game 8ball \
  --mjpeg-port 8080
```

## 3) Monitor live reducer while playing

```bash
watch -n 1 curl -s "http://127.0.0.1:8000/live/state"
```

## 4) Inject manual fouls if needed during match

```bash
curl -s -X POST "http://127.0.0.1:8000/fouls/manual" -H "Content-Type: application/json" -d '{"game_type":"8ball","foul_type":"unsportsmanlike_conduct","player_idx":1,"team_idx":1,"notes":"time violation"}'
```

## 5) Post-game audit

```bash
python - <<'PY'
import sqlite3, json
db="/home/$USER/Billiards-AI/billiards.db"
con=sqlite3.connect(db)
rows=con.execute("select payload from events where json_extract(payload, '$.type') in ('game_over','shot_summary') order by id desc limit 20").fetchall()
print("recent summaries:", len(rows))
for r in rows[:5]:
    e=json.loads(r[0]); print(e.get("type"), e.get("ts"))
PY
```

## Pass criteria

- live state matches observed match result
- game_over appears once with correct winner and reason
- shot summaries exist for major shots

