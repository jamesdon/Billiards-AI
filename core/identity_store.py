from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, Optional

from .types import PlayerProfile, StickProfile


class IdentityStore:
    """
    Very lightweight persistence for remembered players and sticks.

    - Profiles are matched using a simple appearance signature (e.g., HSV histogram).
    - For constrained edge hardware, we avoid heavyweight ReID models by default.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.players: Dict[str, PlayerProfile] = {}
        self.sticks: Dict[str, StickProfile] = {}

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            return
        self.players = {p["id"]: PlayerProfile(**p) for p in d.get("players", [])}
        self.sticks = {s["id"]: StickProfile(**s) for s in d.get("sticks", [])}

    def save(self) -> None:
        d = {
            "players": [asdict(p) for p in self.players.values()],
            "sticks": [asdict(s) for s in self.sticks.values()],
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)

    def get_player(self, profile_id: str) -> Optional[PlayerProfile]:
        return self.players.get(profile_id)

    def get_stick(self, profile_id: str) -> Optional[StickProfile]:
        return self.sticks.get(profile_id)

    def upsert_player(self, profile: PlayerProfile) -> None:
        self.players[profile.id] = profile

    def upsert_stick(self, profile: StickProfile) -> None:
        self.sticks[profile.id] = profile

    def rename_player(self, profile_id: str, display_name: str) -> None:
        p = self.players.get(profile_id)
        if p is None:
            raise KeyError(profile_id)
        self.players[profile_id] = PlayerProfile(id=p.id, display_name=display_name, color_signature=p.color_signature)

    def rename_stick(self, profile_id: str, display_name: str) -> None:
        s = self.sticks.get(profile_id)
        if s is None:
            raise KeyError(profile_id)
        self.sticks[profile_id] = StickProfile(id=s.id, display_name=display_name, color_signature=s.color_signature)

