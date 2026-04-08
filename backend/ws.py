from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Set

from fastapi import WebSocket


@dataclass
class Hub:
    clients: Set[WebSocket] = field(default_factory=set)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    def broadcast_json(self, payload: dict) -> None:
        # Fire-and-forget broadcast
        for ws in list(self.clients):
            asyncio.create_task(self._safe_send(ws, payload))

    async def _safe_send(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            self.disconnect(ws)

