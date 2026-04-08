from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, DefaultDict, List

from .types import Event, EventType


Handler = Callable[[Event], None]


@dataclass
class EventBus:
    _subs: DefaultDict[EventType, List[Handler]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._subs is None:
            self._subs = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._subs.get(event.type, []):
            handler(event)

