# Backend (optional)

## Purpose

- Persist game history and events
- Serve a dashboard/API
- Broadcast live state/events to clients

## Baseline implementation

- FastAPI app: `backend/app.py`
- SQLite storage: `backend/store.py`
- WebSocket hub: `backend/ws.py`
- DynamoDB (optional): `backend/aws_store.py`
- Live reducer: `backend/reducer.py` (`LiveGameReducer`)

## Live state (`GET /live/state`)

`POST /event` feeds the reducer incremental edge events (`shot_start`, `shot_end`, `ball_pocketed`, `ball_collision`, `rail_hit`, `foul`, `shot_summary`, `game_over`). For **accurate** inning / current player / scores, the edge (or a bridge process) should also **`POST /state`** with periodic `GameState` snapshots; the reducer merges overlapping keys from those snapshots so dashboards stay coherent during Phase 9-style monitoring.

## Run

```bash
cd "/home/$USER/Billiards-AI"
./scripts/run_backend.sh
```

The app is `backend.app:app` (FastAPI). **`scripts/run_backend.sh`** wraps **`.venv/bin/python3 -m uvicorn`** with defaults `BACKEND_HOST=127.0.0.1`, `BACKEND_PORT=8000`, a listen-port pre-check, and the same behavior described in **`README.md`**. Raw: `python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000` with venv active.

## AWS stats store (optional)

For persistent per-player shot stats across games, use DynamoDB:

- Partition key: `player_profile_id`
- Sort key: `shot_ts` (ms) or `game_id#shot_idx`

The backend can write a `shot_summary` emitted by the edge pipeline into DynamoDB.

### Stick stats are independent

Because cues are frequently shared (house cues, break cues), **stick stats are not tied to a player**.
Use a separate DynamoDB table for cues:

- Partition key: `stick_profile_id`
- Sort key: `shot_ts` (ms) or `game_id#shot_idx`

Environment variables:

- `BILLIARDS_DDB_PLAYER_TABLE` (or legacy `BILLIARDS_DDB_TABLE`)
- `BILLIARDS_DDB_STICK_TABLE`

