import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.domain import Channel, EvidenceStatus
from src.publishing import GuidanceRef
from src.seed import load_seed_file
from src.service import AdvisoryCenter
from src.validator import validate_event

TZ = timezone(timedelta(hours=8))
SEED = Path(__file__).parents[1] / "data" / "seed.json"
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
T1 = datetime(2026, 9, 20, 10, 0, tzinfo=TZ)
T2 = datetime(2026, 9, 20, 11, 0, tzinfo=TZ)
T3 = datetime(2026, 9, 20, 12, 0, tzinfo=TZ)

REVISED_G1 = (
    "服用辛伐他汀（如舒降之）期间，请避免饮用西柚汁。"
    "最新人体研究进一步确认了血药浓度升高的幅度。"
    "请勿自行停药，如需调整用药请咨询医生或药师。"
)


def make_center() -> AdvisoryCenter:
    center = AdvisoryCenter()
    load_seed_file(center, SEED)
    return center


class PublishingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.center = make_center()
        self.center.publisher.publish(Channel.POSTER, [GuidanceRef("G1", 1)], at=T0, reason="首次发布")
        self.center.publisher.publish(
            Channel.PHARMACY_SCREEN, [GuidanceRef("G1", 1)], at=T0, reason="首次发布"
        )
        self.center.publisher.publish(Channel.ONLINE_QA, [GuidanceRef("G4", 1)], at=T0, reason="首次发布")

    def test_publish_increments_channel_version(self) -> None:
        publication = self.center.publisher.publish(
            Channel.POSTER, [GuidanceRef("G1", 1)], at=T1, reason="例行更新"
        )
        self.assertEqual(publication.publication_version, 2)

    def test_publish_rejects_unapproved_guidance(self) -> None:
        self.center.guidance.withdraw("G2", at=T1, reason="内容合并")
        with self.assertRaises(ValueError):
            self.center.publisher.publish(
                Channel.POSTER, [GuidanceRef("G2", 1)], at=T1, reason="应失败"
            )

    def test_evidence_update_reversions_only_affected_channels(self) -> None:
        center = self.center
        new_evidence, affected = center.update_evidence(
            "E1",
            reviewed_by="陈审校",
            reviewed_at=T1,
            valid_until=date(2028, 6, 30),
            effect="更新后的人体研究表述：升高幅度进一步确认",
        )
        self.assertEqual(new_evidence.version, 2)
        self.assertEqual(affected, ("G1",))
        center.guidance.revise(
            "G1",
            text=REVISED_G1,
            reviewed_by="李审核",
            approved_at=T2,
            valid_until=date(2028, 6, 30),
        )
        report = center.reversion_channels(affected, at=T3, reason="证据 E1 更新换版")
        self.assertEqual(
            {p.channel for p in report.reversioned}, {Channel.POSTER, Channel.PHARMACY_SCREEN}
        )
        self.assertEqual(report.untouched_channels, (Channel.ONLINE_QA,))
        self.assertEqual(center.publisher.current(Channel.POSTER).refs, (GuidanceRef("G1", 2),))
        self.assertEqual(center.publisher.current(Channel.ONLINE_QA).publication_version, 1)
        self.assertEqual(center.evidence.get("E1", 1).status, EvidenceStatus.SUPERSEDED)

    def test_withdrawn_guidance_dropped_on_reevaluate(self) -> None:
        self.center.guidance.withdraw("G1", at=T1, reason="内容合并")
        report = self.center.reversion_channels(("G1",), at=T2, reason="撤回换版")
        poster = self.center.publisher.current(Channel.POSTER)
        self.assertEqual(poster.refs, ())
        self.assertEqual(poster.publication_version, 2)
        self.assertEqual(report.untouched_channels, (Channel.ONLINE_QA,))

    def test_received_notice_keeps_snapshot_and_appends_correction(self) -> None:
        center = self.center
        receipt = center.publisher.deliver("R-1", "G1", at=T0)
        original_text = receipt.text_snapshot
        center.guidance.revise(
            "G1",
            text=REVISED_G1,
            reviewed_by="李审核",
            approved_at=T1,
            valid_until=date(2028, 6, 30),
        )
        updated = center.publisher.correct(
            "R-1",
            reason="措辞随证据更新修订",
            corrected_text=center.guidance.latest("G1").text,
            at=T2,
        )
        self.assertEqual(updated.text_snapshot, original_text)
        self.assertEqual(updated.guidance_version, 1)
        self.assertEqual(len(updated.corrections), 1)
        self.assertEqual(updated.corrections[0].corrected_text, REVISED_G1)
        events = center.log.of_type("NOTICE_CORRECTED")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].aggregate_id, "R-1")

    def test_all_emitted_events_match_contract(self) -> None:
        center = self.center
        center.consult(medication_names=["舒降之"], variety="葡萄柚", form="鲜榨果汁")
        _, affected = center.update_evidence(
            "E1", reviewed_by="陈审校", reviewed_at=T1, valid_until=date(2028, 6, 30)
        )
        center.guidance.revise(
            "G1",
            text=REVISED_G1,
            reviewed_by="李审核",
            approved_at=T2,
            valid_until=date(2028, 6, 30),
        )
        center.reversion_channels(affected, at=T3, reason="证据 E1 更新换版")
        center.publisher.deliver("R-9", "G2", at=T3)
        center.publisher.correct("R-9", reason="示例更正", corrected_text="更正后措辞", at=T3)
        self.assertGreater(len(center.log), 0)
        for event in center.log:
            self.assertEqual(validate_event(event.to_envelope()), [], event.event_id)


if __name__ == "__main__":
    unittest.main()
