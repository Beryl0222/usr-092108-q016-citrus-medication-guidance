import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from src.events import EventLog
from src.validator import validate_event

TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 21, 9, 0, tzinfo=TZ)


def append_sample(log: EventLog):
    return log.append(
        event_type="INGREDIENT_MAPPED",
        aggregate_type="medicine_ingredient",
        aggregate_id="simvastatin",
        occurred_at=NOW,
        version=1,
        summary="归一：舒降之 → 辛伐他汀",
    )


class EventLogTest(unittest.TestCase):
    def test_append_assigns_sequential_ids_and_envelope_validates(self) -> None:
        log = EventLog()
        first = append_sample(log)
        second = append_sample(log)
        self.assertEqual(first.event_id, "evt-000001")
        self.assertEqual(second.event_id, "evt-000002")
        self.assertEqual(validate_event(first.to_envelope()), [])

    def test_rejects_unknown_event_type(self) -> None:
        log = EventLog()
        with self.assertRaises(ValueError):
            log.append(
                event_type="NOT_A_TYPE",
                aggregate_type="medicine_ingredient",
                aggregate_id="x",
                occurred_at=NOW,
                version=1,
                summary="无效类型",
            )

    def test_rejects_non_positive_version(self) -> None:
        log = EventLog()
        with self.assertRaises(ValueError):
            log.append(
                event_type="INGREDIENT_MAPPED",
                aggregate_type="medicine_ingredient",
                aggregate_id="x",
                occurred_at=NOW,
                version=0,
                summary="无效版本",
            )

    def test_events_are_immutable(self) -> None:
        log = EventLog()
        event = append_sample(log)
        with self.assertRaises(FrozenInstanceError):
            event.summary = "原地改写"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
