import unittest
from datetime import date, datetime, timedelta, timezone

from src.domain import (
    Audience,
    EvidenceLevel,
    EvidenceStatement,
    GuidanceKind,
    GuidanceStatus,
    LiteratureRef,
    RiskPopulation,
)
from src.events import EventLog
from src.evidence import EvidenceRegistry
from src.guidance import GuidanceRejected, GuidanceService, lint_text

TZ = timezone(timedelta(hours=8))
APPROVED_AT = datetime(2026, 9, 1, 10, 0, tzinfo=TZ)
VALID_UNTIL = date(2027, 8, 31)

SAFE_TEXT = "服用辛伐他汀期间请避免大量饮用西柚汁。请勿自行停药，如需调整用药请咨询医生或药师。"


def make_service() -> tuple[GuidanceService, EvidenceRegistry]:
    evidence = EvidenceRegistry(EventLog())
    evidence.register(
        EvidenceStatement(
            "E-HUMAN",
            1,
            "furanocoumarin",
            "simvastatin",
            EvidenceLevel.HUMAN_PK,
            "大量饮用西柚汁可升高辛伐他汀血药浓度",
            "长期大量饮用情形",
            (LiteratureRef("L1", "示例引文"),),
            "陈审校",
            APPROVED_AT,
            VALID_UNTIL,
        )
    )
    evidence.register(
        EvidenceStatement(
            "E-VITRO",
            1,
            "naringin",
            "fexofenadine",
            EvidenceLevel.IN_VITRO,
            "体外研究提示可能影响转运",
            "仅体外证据",
            (),
            "陈审校",
            APPROVED_AT,
            VALID_UNTIL,
        )
    )
    service = GuidanceService(evidence, log=EventLog())
    service.register_population(RiskPopulation("elderly", "老年患者（≥65岁）"))
    return service, evidence


def approve_kwargs(**overrides) -> dict:
    base = dict(
        guidance_id="G-1",
        kind=GuidanceKind.MEDICATION_SAFETY,
        audience=Audience.PATIENT,
        text=SAFE_TEXT,
        evidence_ids=("E-HUMAN",),
        population_ids=("elderly",),
        reviewed_by="李审核",
        approved_at=APPROVED_AT,
        valid_until=VALID_UNTIL,
    )
    base.update(overrides)
    return base


class GuardrailTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service, self.evidence = make_service()

    def approve(self, **overrides):
        return self.service.approve(**approve_kwargs(**overrides))

    def test_approve_ok(self) -> None:
        version = self.approve()
        self.assertEqual(version.version, 1)
        self.assertEqual(version.status, GuidanceStatus.APPROVED)

    def test_directive_stop_wording_rejected(self) -> None:
        with self.assertRaises(GuidanceRejected) as ctx:
            self.approve(text="血药浓度可能升高，建议停药观察。")
        self.assertIn("禁止指令性停药换药", {issue.rule for issue in ctx.exception.issues})

    def test_directive_switch_wording_rejected(self) -> None:
        with self.assertRaises(GuidanceRejected) as ctx:
            self.approve(text="如需降脂，可改用其他药物。")
        self.assertIn("禁止指令性停药换药", {issue.rule for issue in ctx.exception.issues})

    def test_diagnosis_wording_rejected(self) -> None:
        with self.assertRaises(GuidanceRejected) as ctx:
            self.approve(text="出现肌肉酸痛说明您患有横纹肌溶解症。")
        self.assertIn("禁止推断诊断", {issue.rule for issue in ctx.exception.issues})

    def test_negation_and_consult_wording_allowed(self) -> None:
        issues = lint_text(SAFE_TEXT, levels=(EvidenceLevel.HUMAN_PK,))
        self.assertEqual(issues, [])

    def test_low_level_evidence_requires_uncertainty_and_consult(self) -> None:
        with self.assertRaises(GuidanceRejected) as ctx:
            self.approve(evidence_ids=("E-VITRO",), text="柚子会影响药物吸收，请注意。")
        rules = {issue.rule for issue in ctx.exception.issues}
        self.assertIn("低等级证据须标注不确定性", rules)
        self.assertIn("低等级证据须引导咨询", rules)
        ok = self.approve(
            evidence_ids=("E-VITRO",),
            text="体外研究提示柚子成分可能影响药物吸收，但人体证据有限、尚不确定。请勿自行停药，请咨询医生或药师。",
        )
        self.assertEqual(ok.status, GuidanceStatus.APPROVED)

    def test_safety_guidance_requires_evidence_and_population(self) -> None:
        with self.assertRaises(GuidanceRejected):
            self.approve(evidence_ids=())
        with self.assertRaises(GuidanceRejected):
            self.approve(population_ids=())

    def test_reviewer_and_validity_required(self) -> None:
        with self.assertRaises(GuidanceRejected):
            self.approve(reviewed_by="")
        with self.assertRaises(GuidanceRejected):
            self.approve(valid_until=date(2026, 1, 1))

    def test_unknown_population_rejected(self) -> None:
        with self.assertRaises(GuidanceRejected):
            self.approve(population_ids=("not-registered",))

    def test_retired_evidence_cannot_back_new_guidance(self) -> None:
        self.evidence.retire("E-VITRO", at=APPROVED_AT, reason="被更系统的研究取代")
        with self.assertRaises(GuidanceRejected) as ctx:
            self.approve(
                evidence_ids=("E-VITRO",),
                text="体外研究提示……人体证据有限……请咨询医生或药师。",
            )
        self.assertIn("证据非现行", {issue.rule for issue in ctx.exception.issues})

    def test_revise_keeps_history_and_supersedes_old(self) -> None:
        self.approve()
        revised = self.service.revise(
            "G-1",
            text="服用辛伐他汀期间请避免饮用西柚汁，具体用药问题请咨询医生或药师。",
            reviewed_by="李审核",
            approved_at=datetime(2026, 9, 10, 9, 0, tzinfo=TZ),
            valid_until=VALID_UNTIL,
        )
        self.assertEqual(revised.version, 2)
        old = self.service.get("G-1", 1)
        self.assertEqual(old.status, GuidanceStatus.SUPERSEDED)
        self.assertEqual(old.text, SAFE_TEXT)
        self.assertEqual(self.service.latest("G-1").version, 2)

    def test_withdraw_then_revise_rejected(self) -> None:
        self.approve()
        withdrawn = self.service.withdraw(
            "G-1", at=datetime(2026, 9, 15, 9, 0, tzinfo=TZ), reason="内容合并"
        )
        self.assertEqual(withdrawn.status, GuidanceStatus.WITHDRAWN)
        with self.assertRaises(GuidanceRejected):
            self.service.revise(
                "G-1",
                text="试图修订已撤回提示",
                reviewed_by="李审核",
                approved_at=datetime(2026, 9, 16, 9, 0, tzinfo=TZ),
                valid_until=VALID_UNTIL,
            )


if __name__ == "__main__":
    unittest.main()
