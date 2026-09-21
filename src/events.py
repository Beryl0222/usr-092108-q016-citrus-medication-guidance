"""领域事件的追加式日志：事件一旦写入即不可改写，业务更正产生后继记录。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count

from .validator import validate_event


@dataclass(frozen=True)
class Event:
    """已接收的领域事件，含基础信封与业务负载。"""

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    occurred_at: str
    version: int
    summary: str
    payload: dict = field(default_factory=dict)


class EventLog:
    """只追加的事件日志，写入前用基础信封约定校验。"""

    def __init__(self, clock=None) -> None:
        self._events: list[Event] = []
        self._seq = count(1)
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def append(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        version: int,
        summary: str,
        payload: dict | None = None,
    ) -> Event:
        record = {
            "event_id": f"evt-{next(self._seq):06d}",
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "occurred_at": self._clock(),
            "version": version,
            "summary": summary,
        }
        errors = validate_event(record)
        if errors:
            raise ValueError("事件信封不合法：" + "；".join(errors))
        event = Event(**record, payload=dict(payload or {}))
        self._events.append(event)
        return event

    def all(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def for_aggregate(self, aggregate_id: str) -> tuple[Event, ...]:
        return tuple(e for e in self._events if e.aggregate_id == aggregate_id)
