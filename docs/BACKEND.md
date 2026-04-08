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

## Run

```bash
cd "/home/$USER/Billiards AI"
source .venv/bin/activate
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

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

