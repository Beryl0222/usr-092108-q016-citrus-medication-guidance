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


class SeedFlowTest(unittest.TestCase):
    """端到端：归一 → 查询 → 证据更新 → 修订措辞 → 按影响范围换版 → 追加更正。"""

    def setUp(self) -> None:
        self.center = AdvisoryCenter()
        load_seed_file(self.center, SEED)

    def test_consult_emits_normalization_events(self) -> None:
        result = self.center.consult(
            medication_names=["舒降之"], variety="葡萄柚", form="鲜榨果汁"
        )
        self.assertIn("G1", {item.guidance_id for item in result.items})
        mapped = self.center.log.of_type("INGREDIENT_MAPPED")
        self.assertTrue(any(e.aggregate_type == "medicine_ingredient" for e in mapped))
        self.assertTrue(any(e.aggregate_type == "food_component" for e in mapped))

    def test_pomelo_also_flags_furanocoumarin(self) -> None:
        result = self.center.consult(
            medication_names=["辛伐他汀"], variety="文旦", form="鲜果"
        )
        self.assertIn("G1", {item.guidance_id for item in result.items})

    def test_in_vitro_only_guidance_carries_uncertainty_wording(self) -> None:
        result = self.center.consult(
            medication_names=["阿特拉"], variety="西柚", form="果汁"
        )
        g3 = next(item for item in result.items if item.guidance_id == "G3")
        self.assertIn("证据有限", g3.text)
        self.assertIn("咨询", g3.text)

    def test_full_update_reversion_correction_flow(self) -> None:
        center = self.center
        t0 = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
        center.publisher.publish(Channel.POSTER, [GuidanceRef("G1", 1)], at=t0, reason="首次发布")
        center.publisher.publish(
            Channel.ONLINE_QA, [GuidanceRef("G2", 1)], at=t0, reason="首次发布"
        )
        receipt = center.publisher.deliver("R-100", "G1", at=t0)
        snapshot = receipt.text_snapshot

        new_evidence, affected = center.update_evidence(
            "E1",
            reviewed_by="陈审校",
            reviewed_at=datetime(2026, 9, 20, 10, 0, tzinfo=TZ),
            valid_until=date(2028, 6, 30),
            effect="更新后的人体研究表述",
        )
        self.assertEqual(new_evidence.version, 2)
        self.assertEqual(center.evidence.get("E1", 1).status, EvidenceStatus.SUPERSEDED)
        self.assertEqual(affected, ("G1",))

        center.guidance.revise(
            "G1",
            text="服用辛伐他汀（如舒降之）期间，请避免饮用西柚汁。请勿自行停药，如需调整用药请咨询医生或药师。",
            reviewed_by="李审核",
            approved_at=datetime(2026, 9, 20, 11, 0, tzinfo=TZ),
            valid_until=date(2028, 6, 30),
        )
        report = center.reversion_channels(
            affected, at=datetime(2026, 9, 20, 12, 0, tzinfo=TZ), reason="证据 E1 更新换版"
        )
        self.assertEqual([p.channel for p in report.reversioned], [Channel.POSTER])
        self.assertEqual(report.untouched_channels, (Channel.ONLINE_QA,))
        self.assertEqual(center.publisher.current(Channel.POSTER).refs, (GuidanceRef("G1", 2),))

        corrected = center.publisher.correct(
            "R-100",
            reason="措辞随证据更新修订",
            corrected_text=center.guidance.latest("G1").text,
            at=datetime(2026, 9, 20, 13, 0, tzinfo=TZ),
        )
        self.assertEqual(corrected.text_snapshot, snapshot)
        self.assertEqual(len(corrected.corrections), 1)

        for event in center.log:
            self.assertEqual(validate_event(event.to_envelope()), [], event.event_id)


if __name__ == "__main__":
    unittest.main()
