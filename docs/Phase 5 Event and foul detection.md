# Phase 5: Event and foul detection

## Goal

Validate event stream and foul logic (auto + manual injection).

## 1) Start backend

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## 2) Inject manual foul (pool)

```bash
curl -s -X POST "http://127.0.0.1:8000/fouls/manual" \
  -H "Content-Type: application/json" \
  -d '{"game_type":"8ball","foul_type":"touched_ball","player_idx":0,"team_idx":0,"notes":"ref touch foul"}'
```

## 3) Inject manual foul (snooker with points)

```bash
curl -s -X POST "http://127.0.0.1:8000/fouls/manual" \
  -H "Content-Type: application/json" \
  -d '{"game_type":"snooker","foul_type":"no_foot_on_floor","player_idx":0,"team_idx":0,"foul_points":6}'
```

## 4) Verify live reducer changed

```bash
curl -s "http://127.0.0.1:8000/live/state"
```

## 5) Verify event persistence

```bash
python - <<'PY'
import sqlite3, json
db="/home/$USER/Billiards-AI/billiards.db"
con=sqlite3.connect(db)
rows=con.execute("select id, ts, payload from events order by id desc limit 5").fetchall()
for r in rows:
    print(r[0], r[1], json.loads(r[2]).get("type"))
PY
```

## Pass criteria

- foul event persisted
- live reducer updates foul counts and penalty model fields

