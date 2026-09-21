"""领域事件与追加式事件日志。

事件一旦写入即不可改写；业务更正通过后继事件表达（如 NOTICE_CORRECTED）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

EVENT_TYPES = (
    "INGREDIENT_MAPPED",
    "EVIDENCE_REVIEWED",
    "GUIDANCE_APPROVED",
    "GUIDANCE_WITHDRAWN",
    "CHANNEL_UPDATED",
    "NOTICE_CORRECTED",
)

AGGREGATE_TYPES = (
    "food_component",
    "medicine_ingredient",
    "evidence_statement",
    "guidance_version",
    "channel_publication",
    "received_notice",
)


@dataclass(frozen=True)
class DomainEvent:
    """符合 contracts/domain.schema.json 信封约定的事件。"""

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    occurred_at: datetime
    version: int
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_envelope(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "occurred_at": self.occurred_at.isoformat(),
            "version": self.version,
            "summary": self.summary,
        }
        envelope.update(self.payload)
        return envelope


class EventLog:
    """只增不改的事件日志。"""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    def append(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        occurred_at: datetime,
        version: int,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> DomainEvent:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"未知事件类型：{event_type}")
        if aggregate_type not in AGGREGATE_TYPES:
            raise ValueError(f"未知聚合类型：{aggregate_type}")
        if not isinstance(version, int) or version < 1:
            raise ValueError("version 必须是正整数")
        if not summary:
            raise ValueError("summary 不能为空")
        event = DomainEvent(
            event_id=f"evt-{len(self._events) + 1:06d}",
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            occurred_at=occurred_at,
            version=version,
            summary=summary,
            payload=dict(payload or {}),
        )
        self._events.append(event)
        return event

    def of_type(self, event_type: str) -> list[DomainEvent]:
        return [event for event in self._events if event.event_type == event_type]

    def __iter__(self) -> Iterator[DomainEvent]:
        return iter(tuple(self._events))

    def __len__(self) -> int:
        return len(self._events)
