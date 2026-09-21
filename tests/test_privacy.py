import unittest

from src.models import ContentType
from src.privacy import build_query, patient_view
from tests.support import approve_safety_guidance, build_service


class PrivacyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = build_service()
        approve_safety_guidance(self.service)

    def test_query_carries_only_minimal_information(self) -> None:
        # 查询只含归一后的成分标识与必要人群信息，不含病历、诊断或身份
        query, _ = build_query(
            [("舒降之", None)], self.service.registry, risk_population="老年人"
        )
        self.assertEqual(query.ingredient_ids, ("ing-sim",))
        self.assertEqual(query.risk_population, "老年人")
        self.assertEqual(set(vars(query)), {"ingredient_ids", "risk_population"})

    def test_patient_view_distinguishes_content_types(self) -> None:
        guidance = self.service._guidance["g-1"]
        view = patient_view(guidance)
        self.assertEqual(view["content_type"], ContentType.MEDICATION_SAFETY.value)
        self.assertEqual(set(view), {"content_type", "certainty", "text", "valid_until"})

    def test_pharmacist_can_trace_evidence_and_applicability(self) -> None:
        trace = self.service.trace("g-1")
        self.assertEqual(trace["reviewer"], "药师甲")
        self.assertEqual(trace["risk_populations"], ("老年人", "肝功能不全者"))
        evidence = trace["evidence"][0]
        self.assertEqual(evidence["source"], "某临床药理研究（人体）")
        self.assertIn("200ml", evidence["applicability"])
        self.assertEqual(evidence["pathway"], "CYP3A4")


if __name__ == "__main__":
    unittest.main()
