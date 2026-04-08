from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import boto3


@dataclass
class DynamoStatsStore:
    """
    DynamoDB store for per-player shot stats.

    Table design (recommended):
    - PK: player_profile_id (string)
    - SK: shot_ts (number) OR game_id#shot_idx (string)
    - Attributes: shot tags, metrics, game metadata
    """

    table_name: str
    region_name: Optional[str] = None

    def __post_init__(self) -> None:
        self.ddb = boto3.resource("dynamodb", region_name=self.region_name)
        self.table = self.ddb.Table(self.table_name)

    def put_shot_summary(self, player_profile_id: str, shot_ts: float, payload: Dict[str, Any]) -> None:
        item = {
            "player_profile_id": player_profile_id,
            "shot_ts": int(shot_ts * 1000),
            "ingested_at": int(time.time() * 1000),
            "record_type": "shot_summary",
            **payload,
        }
        self.table.put_item(Item=item)

    def put_game_summary(self, player_profile_id: str, game_end_ts: float, payload: Dict[str, Any]) -> None:
        item = {
            "player_profile_id": player_profile_id,
            "shot_ts": int(game_end_ts * 1000),
            "ingested_at": int(time.time() * 1000),
            "record_type": "game_summary",
            **payload,
        }
        self.table.put_item(Item=item)


@dataclass
class DynamoStickStatsStore:
    """
    DynamoDB store for per-stick shot stats (NOT tied to any player).

    Table design (recommended):
    - PK: stick_profile_id (string)
    - SK: shot_ts (number) OR game_id#shot_idx (string)
    - Attributes: shot tags, metrics, game metadata
    """

    table_name: str
    region_name: Optional[str] = None

    def __post_init__(self) -> None:
        self.ddb = boto3.resource("dynamodb", region_name=self.region_name)
        self.table = self.ddb.Table(self.table_name)

    def put_shot_summary(self, stick_profile_id: str, shot_ts: float, payload: Dict[str, Any]) -> None:
        item = {
            "stick_profile_id": stick_profile_id,
            "shot_ts": int(shot_ts * 1000),
            "ingested_at": int(time.time() * 1000),
            **payload,
        }
        self.table.put_item(Item=item)

