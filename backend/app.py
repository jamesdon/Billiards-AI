from __future__ import annotations

import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .aws_store import DynamoStatsStore, DynamoStickStatsStore
from .fouls import ManualFoulRequest, build_manual_foul_event
from .profiles import router as profiles_router
from .reducer import LiveGameReducer
from .store import Store
from .ws import Hub


def create_app() -> FastAPI:
    app = FastAPI(title="Billiards AI Backend", version="0.1")
    app.include_router(profiles_router)
    store = Store("billiards.db")
    hub = Hub()
    reducer = LiveGameReducer()
    ddb_table = os.environ.get("BILLIARDS_DDB_TABLE")  # legacy: player table
    ddb_player_table = os.environ.get("BILLIARDS_DDB_PLAYER_TABLE") or ddb_table
    ddb_stick_table = os.environ.get("BILLIARDS_DDB_STICK_TABLE")
    ddb_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    ddb_player = DynamoStatsStore(table_name=ddb_player_table, region_name=ddb_region) if ddb_player_table else None
    ddb_stick = DynamoStickStatsStore(table_name=ddb_stick_table, region_name=ddb_region) if ddb_stick_table else None

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/event")
    def ingest_event(event: dict):
        store.insert_event(event)
        live_state = reducer.ingest_event(event)
        # Persist stats to Dynamo when configured.
        if ddb_player is not None or ddb_stick is not None:
            try:
                if event.get("type") == "shot_summary":
                    ss = event.get("payload", {}).get("shot_summary") or event.get("shot_summary")
                    if isinstance(ss, dict):
                        pid = ss.get("shooter_profile_id")
                        sid = ss.get("stick_profile_id")
                        ts = float(ss.get("ts_start", event.get("ts", 0.0)))
                        if pid and ddb_player is not None:
                            ddb_player.put_shot_summary(player_profile_id=str(pid), shot_ts=ts, payload=ss)
                        if sid and ddb_stick is not None:
                            ddb_stick.put_shot_summary(stick_profile_id=str(sid), shot_ts=ts, payload=ss)
                if event.get("type") == "game_over" and ddb_player is not None:
                    gs = event.get("payload", {}) or {}
                    ts = float(event.get("ts", 0.0))
                    # Write a copy of end-of-game stats under each participating player profile id.
                    for p in gs.get("players", []):
                        pid = p.get("profile_id")
                        if pid:
                            ddb_player.put_game_summary(player_profile_id=str(pid), game_end_ts=ts, payload=gs)
            except Exception:
                # Best-effort; backend should keep running even if AWS is misconfigured.
                pass
        hub.broadcast_json({"type": "event", "data": event})
        hub.broadcast_json({"type": "live_state", "data": live_state})
        return {"ok": True}

    @app.post("/fouls/manual")
    def inject_manual_foul(req: ManualFoulRequest):
        event = build_manual_foul_event(req)
        store.insert_event(event)
        live_state = reducer.ingest_event(event)
        hub.broadcast_json({"type": "event", "data": event})
        hub.broadcast_json({"type": "live_state", "data": live_state})
        return {"ok": True, "event": event, "live_state": live_state}

    @app.post("/state")
    def ingest_state(state: dict):
        store.insert_state(state)
        live_state = reducer.ingest_state(state)
        hub.broadcast_json({"type": "state", "data": state})
        hub.broadcast_json({"type": "live_state", "data": live_state})
        return {"ok": True}

    @app.get("/live/state")
    def get_live_state():
        return reducer.state

    @app.post("/live/reset")
    def reset_live_state():
        reducer.reset()
        hub.broadcast_json({"type": "live_state", "data": reducer.state})
        return {"ok": True, "live_state": reducer.state}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await hub.connect(websocket)
        try:
            while True:
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(websocket)

    return app


app = create_app()

