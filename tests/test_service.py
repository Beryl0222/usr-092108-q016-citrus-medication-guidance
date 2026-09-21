import unittest

from src.models import Certainty, ContentType
from src.privacy import build_query
from tests.support import VALID_FROM, VALID_UNTIL, approve_safety_guidance, build_service


class ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = build_service()

    def test_in_vitro_evidence_cannot_back_confirmed_safety_guidance(self) -> None:
        with self.assertRaises(ValueError):
            self.service.approve_guidance(
                "g-bad",
                ContentType.MEDICATION_SAFETY,
                "服用氨氯地平期间不能吃柚子，请咨询医生或药师。",
                ("ev-2",),  # 仅细胞实验证据
                reviewer="药师甲",
                valid_from=VALID_FROM,
                valid_until=VALID_UNTIL,
            )

    def test_forbidden_wording_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.approve_guidance(
                "g-bad2",
                ContentType.MEDICATION_SAFETY,
                "吃柚子期间建议停药。",
                ("ev-1",),
                reviewer="药师甲",
                valid_from=VALID_FROM,
                valid_until=VALID_UNTIL,
            )

    def test_reviewer_and_validity_are_required(self) -> None:
        with self.assertRaises(ValueError):
            self.service.approve_guidance(
                "g-bad3", ContentType.NUTRITION_GENERAL, "一般营养知识。",
                (), reviewer="", valid_from=VALID_FROM, valid_until=VALID_UNTIL,
            )
        with self.assertRaises(ValueError):
            self.service.approve_guidance(
                "g-bad4", ContentType.NUTRITION_GENERAL, "一般营养知识。",
                (), reviewer="药师甲", valid_from=VALID_UNTIL, valid_until=VALID_FROM,
            )

    def test_answer_matches_confirmed_ingredient(self) -> None:
        approve_safety_guidance(self.service)
        query, results = build_query([("舒降之", None)], self.service.registry)
        answer = self.service.answer(query)
        self.assertFalse(answer.uncertain)
        self.assertEqual(answer.items[0]["content_type"], "medication_safety")

    def test_unconfirmable_product_yields_uncertainty(self) -> None:
        approve_safety_guidance(self.service)
        # 商品换了未登记的新配方：归一不确定，答复只表达不确定并引导咨询
        query, results = build_query([("某品牌降脂胶囊", "2026版")], self.service.registry)
        self.assertEqual(results[0].certainty, Certainty.UNCERTAIN)
        answer = self.service.answer(query)
        self.assertTrue(answer.uncertain)
        self.assertIn("请咨询医生或药师", answer.note)

    def test_events_are_append_only_and_traceable(self) -> None:
        approve_safety_guidance(self.service)
        types = [e.event_type for e in self.service.events.all()]
        self.assertIn("INGREDIENT_MAPPED", types)
        self.assertIn("EVIDENCE_REVIEWED", types)
        self.assertIn("GUIDANCE_APPROVED", types)


if __name__ == "__main__":
    unittest.main()
