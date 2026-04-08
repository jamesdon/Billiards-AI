from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class LiveGameReducer:
    """
    Backend canonical game-state reducer.

    Keeps a lightweight authoritative state for UI/ops:
    - players/teams scoreboard
    - inning/shot counters
    - foul bookkeeping and ball-in-hand target
    - latest event metadata
    """

    state: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.state:
            self.reset()

    def reset(self) -> None:
        self.state = {
            "game_type": None,
            "play_mode": None,
            "rulesets": {},
            "inning": 1,
            "shot_count": 0,
            "players": [],
            "teams": [],
            "winner_team": None,
            "game_over_reason": None,
            "ball_in_hand_for_team": None,
            "latest_event": None,
            "updated_ts": 0.0,
        }

    def ingest_state(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        # Prefer explicit edge snapshot as canonical base when available.
        self.state["updated_ts"] = float(snapshot.get("ts", self.state["updated_ts"]))
        for k in ("game_type", "play_mode", "rulesets", "inning", "shot_count", "winner_team", "game_over_reason"):
            if k in snapshot:
                self.state[k] = snapshot[k]
        if "players" in snapshot and isinstance(snapshot["players"], list):
            self.state["players"] = snapshot["players"]
        if "teams" in snapshot and isinstance(snapshot["teams"], list):
            self.state["teams"] = snapshot["teams"]
        return self.state

    def ingest_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        et = str(event.get("type", "")).lower()
        payload = event.get("payload", {}) or {}
        ts = float(event.get("ts", 0.0))
        self.state["latest_event"] = {"type": et, "payload": payload}
        self.state["updated_ts"] = ts

        if et == "game_over":
            self._apply_game_over(payload)
        elif et == "shot_summary":
            self.state["shot_count"] = max(int(self.state.get("shot_count", 0)), 1)
        elif et == "foul":
            self._apply_foul(payload)

        return self.state

    def _apply_game_over(self, payload: Dict[str, Any]) -> None:
        self.state["game_type"] = payload.get("game_type", self.state.get("game_type"))
        self.state["play_mode"] = payload.get("play_mode", self.state.get("play_mode"))
        self.state["rulesets"] = payload.get("rulesets", self.state.get("rulesets", {}))
        self.state["winner_team"] = payload.get("winner_team")
        self.state["game_over_reason"] = payload.get("game_over_reason")
        self.state["inning"] = payload.get("inning", self.state.get("inning"))
        self.state["shot_count"] = payload.get("shot_count", self.state.get("shot_count"))
        if isinstance(payload.get("players"), list):
            self.state["players"] = payload["players"]
        if isinstance(payload.get("teams"), list):
            self.state["teams"] = payload["teams"]

    def _apply_foul(self, payload: Dict[str, Any]) -> None:
        player_idx = payload.get("player_idx")
        team_idx = payload.get("team_idx")
        penalty_model = payload.get("penalty_model")
        foul_points = int(payload.get("foul_points", 4))

        if isinstance(player_idx, int) and 0 <= player_idx < len(self.state["players"]):
            p = self.state["players"][player_idx]
            p["fouls"] = int(p.get("fouls", 0)) + 1

        if isinstance(team_idx, int) and 0 <= team_idx < len(self.state["teams"]):
            t = self.state["teams"][team_idx]
            t["fouls"] = int(t.get("fouls", 0)) + 1

        if penalty_model == "snooker_points":
            # Award points to opponent based on provided context.
            if isinstance(player_idx, int) and len(self.state["players"]) >= 2:
                opp = 1 - player_idx if player_idx in (0, 1) else None
                if opp is not None and 0 <= opp < len(self.state["players"]):
                    p = self.state["players"][opp]
                    p["score"] = int(p.get("score", 0)) + foul_points
            elif isinstance(team_idx, int) and len(self.state["teams"]) >= 2:
                opp = 1 - team_idx if team_idx in (0, 1) else None
                if opp is not None and 0 <= opp < len(self.state["teams"]):
                    t = self.state["teams"][opp]
                    t["score"] = int(t.get("score", 0)) + foul_points
        elif penalty_model == "ball_in_hand":
            # Opponent side gets ball-in-hand (2-team baseline).
            if isinstance(team_idx, int):
                self.state["ball_in_hand_for_team"] = 1 - team_idx if team_idx in (0, 1) else None
            elif isinstance(player_idx, int):
                self.state["ball_in_hand_for_team"] = 1 - player_idx if player_idx in (0, 1) else None

