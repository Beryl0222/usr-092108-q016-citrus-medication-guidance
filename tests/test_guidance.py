import unittest

from src.guidance import (
    CONSULT_GUIDANCE,
    UNCERTAIN_TEXT,
    check_wording,
    limited_evidence_text,
    supports_patient_safety_advice,
)
from src.models import EvidenceLevel, EvidenceStatement


def evidence(level: EvidenceLevel) -> EvidenceStatement:
    return EvidenceStatement(
        evidence_id="ev-x",
        component_id="fc-1",
        ingredient_id="ing-sim",
        level=level,
        finding="某结论",
        source="某文献",
        applicability="某边界",
    )


class WordingTest(unittest.TestCase):
    def test_forbidden_patterns_are_flagged(self) -> None:
        for text in ("建议停药观察", "可改服其他药物", "诊断为高血脂"):
            self.assertTrue(check_wording(text), text)

    def test_consult_wording_is_allowed(self) -> None:
        # “不要自行调整用药”是引导咨询，不是指使停药
        self.assertEqual(check_wording(UNCERTAIN_TEXT), [])

    def test_uncertain_text_guides_to_consult(self) -> None:
        self.assertIn(CONSULT_GUIDANCE, UNCERTAIN_TEXT)

    def test_limited_evidence_text_blocks_personal_adjustment(self) -> None:
        text = limited_evidence_text(EvidenceLevel.IN_VITRO)
        self.assertIn("尚不能作为个人用药调整的依据", text)
        self.assertIn(CONSULT_GUIDANCE, text)

    def test_only_human_or_consensus_evidence_is_actionable(self) -> None:
        self.assertTrue(supports_patient_safety_advice(evidence(EvidenceLevel.HUMAN_CLINICAL)))
        self.assertTrue(supports_patient_safety_advice(evidence(EvidenceLevel.EXPERT_CONSENSUS)))
        self.assertFalse(supports_patient_safety_advice(evidence(EvidenceLevel.IN_VITRO)))
        self.assertFalse(supports_patient_safety_advice(evidence(EvidenceLevel.ANIMAL)))


if __name__ == "__main__":
    unittest.main()
