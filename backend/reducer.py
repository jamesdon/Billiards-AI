from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


def _append_bounded(lst: List[Any], item: Any, maxlen: int = 32) -> None:
    lst.append(item)
    if len(lst) > maxlen:
        del lst[0 : len(lst) - maxlen]


@dataclass
class LiveGameReducer:
    """
    Backend canonical game-state reducer.

    Keeps a lightweight authoritative state for UI/ops:
    - players/teams scoreboard
    - inning/shot counters
    - foul bookkeeping and ball-in-hand target
    - latest event metadata
    - shot lifecycle + recent physics-ish events (pocket/collision/rail)

    Full turn order and scores still come from **POST /state** snapshots when the edge
    publishes `GameState`; this reducer merges incremental **POST /event** updates so
    `GET /live/state` is useful between snapshots.
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
            "current_player_idx": 0,
            "current_team_idx": 0,
            "players": [],
            "teams": [],
            "winner_team": None,
            "game_over_reason": None,
            "ball_in_hand_for_team": None,
            "in_shot": False,
            "rail_hits_this_shot": 0,
            "recent_ball_pockets": [],
            "recent_collisions": [],
            "recent_rail_hits": [],
            "latest_event": None,
            "updated_ts": 0.0,
            "last_player_shot_over_ts": None,
            "seconds_since_previous_shot_over": None,
        }

    def ingest_state(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        # Prefer explicit edge snapshot as canonical base when available.
        self.state["updated_ts"] = float(snapshot.get("ts", self.state["updated_ts"]))
        for k in (
            "game_type",
            "play_mode",
            "rulesets",
            "inning",
            "shot_count",
            "winner_team",
            "game_over_reason",
            "current_player_idx",
            "current_team_idx",
            "ball_in_hand_for_team",
            "in_shot",
        ):
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
        elif et == "shot_start":
            self.state["in_shot"] = True
            self.state["rail_hits_this_shot"] = 0
            for k in ("current_player_idx", "current_team_idx"):
                if k in payload and isinstance(payload[k], int):
                    self.state[k] = payload[k]
        elif et == "shot_end":
            self.state["in_shot"] = False
            self.state["shot_count"] = int(self.state.get("shot_count", 0)) + 1
            for k in ("current_player_idx", "current_team_idx", "inning", "ball_in_hand_for_team"):
                if k in payload and isinstance(payload[k], int):
                    self.state[k] = payload[k]
        elif et == "ball_pocketed":
            _append_bounded(
                self.state["recent_ball_pockets"],
                {
                    "ball_id": payload.get("ball_id"),
                    "pocket_label": payload.get("pocket_label"),
                    "ts": ts,
                },
            )
        elif et == "ball_collision":
            _append_bounded(
                self.state["recent_collisions"],
                {"a": payload.get("a"), "b": payload.get("b"), "ts": ts},
            )
        elif et == "rail_hit":
            self.state["rail_hits_this_shot"] = int(self.state.get("rail_hits_this_shot", 0)) + 1
            _append_bounded(
                self.state["recent_rail_hits"],
                {"ball_id": payload.get("ball_id"), "rail": payload.get("rail"), "ts": ts},
            )
        elif et == "player_turn_begin":
            for k in ("current_player_idx", "current_team_idx"):
                if k in payload and isinstance(payload[k], int):
                    self.state[k] = payload[k]
        elif et == "player_turn_over":
            # Turn authority moves on the following `player_turn_begin`; keep timestamp only.
            pass
        elif et == "player_shot_over":
            self.state["last_player_shot_over_ts"] = ts
        elif et == "player_shot_begin":
            if "seconds_since_previous_shot_over" in payload:
                self.state["seconds_since_previous_shot_over"] = payload.get("seconds_since_previous_shot_over")
        elif et == "achievement":
            # Counts live on edge `PlayerState.achievement_counts`; avoid double-counting here.
            pass

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
        if player_idx is None and isinstance(payload.get("shooter_player_idx"), int):
            player_idx = payload.get("shooter_player_idx")
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

