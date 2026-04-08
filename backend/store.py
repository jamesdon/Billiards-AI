from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Store:
    path: str

    def __post_init__(self) -> None:
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, payload TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS states (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, payload TEXT)"
        )
        self._conn.commit()

    def insert_event(self, event: Dict[str, Any]) -> None:
        ts = float(event.get("ts", 0.0))
        self._conn.execute("INSERT INTO events (ts, payload) VALUES (?, ?)", (ts, json.dumps(event)))
        self._conn.commit()

    def insert_state(self, state: Dict[str, Any]) -> None:
        ts = float(state.get("ts", 0.0))
        self._conn.execute("INSERT INTO states (ts, payload) VALUES (?, ?)", (ts, json.dumps(state)))
        self._conn.commit()

