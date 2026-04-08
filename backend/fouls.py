from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/fouls", tags=["fouls"])


class ManualFoulRequest(BaseModel):
    game_type: str  # 8ball, 9ball, straight_pool, uk_pool, snooker
    foul_type: str
    player_idx: Optional[int] = None
    team_idx: Optional[int] = None
    notes: Optional[str] = None
    # Snooker-specific override (defaults to 4 when omitted)
    foul_points: Optional[int] = None


def build_manual_foul_event(req: ManualFoulRequest) -> dict:
    payload = {
        "source": "manual_referee",
        "foul_type": req.foul_type,
        "player_idx": req.player_idx,
        "team_idx": req.team_idx,
        "notes": req.notes,
    }
    gt = req.game_type.lower().strip()
    if gt == "snooker":
        payload["penalty_model"] = "snooker_points"
        payload["foul_points"] = int(req.foul_points) if req.foul_points is not None else 4
    else:
        payload["penalty_model"] = "ball_in_hand"
    return {"type": "foul", "ts": time.time(), "payload": payload}

