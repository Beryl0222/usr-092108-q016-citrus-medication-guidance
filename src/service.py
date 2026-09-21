"""发布服务门面：把归一、证据、措辞、发布与更正串成一条可追溯的流。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .events import Event, EventLog
from .guidance import UNCERTAIN_TEXT, check_wording, supports_patient_safety_advice
from .models import (
    Certainty,
    ContentType,
    EvidenceStatement,
    FoodComponent,
    GuidanceVersion,
    MedicineIngredient,
)
from .normalization import IngredientRegistry
from .privacy import MedicationQuery, patient_view, pharmacist_trace
from .publishing import Channel, ChannelRegistry, PatientReceipt


@dataclass(frozen=True)
class PatientAnswer:
    """面向患者的答复：按内容类型分组的提示，或标准不确定表述。"""

    items: tuple[dict, ...]
    uncertain: bool
    note: str


class GuidanceService:
    """区域药学中心的食物与用药提示发布服务。"""

    def __init__(self, clock=None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.events = EventLog(self._clock)
        self.registry = IngredientRegistry()
        self.channels = ChannelRegistry()
        self._components: dict[str, FoodComponent] = {}
        self._evidence: dict[str, EvidenceStatement] = {}
        self._guidance: dict[str, GuidanceVersion] = {}  # 每个提示的最新版本

    # ---- 登记：成分、商品配方与柑橘活性成分 ----

    def register_ingredient(self, ingredient: MedicineIngredient) -> Event:
        self.registry.register_ingredient(ingredient)
        return self.events.append(
            "INGREDIENT_MAPPED",
            "medicine_ingredient",
            ingredient.ingredient_id,
            1,
            f"登记药物成分 {ingredient.name} 及其别名与代谢途径",
            {"aliases": ingredient.aliases, "pathways": ingredient.metabolic_pathways},
        )

    def register_product(
        self, product_name: str, formulation: str, ingredient_ids: tuple[str, ...]
    ) -> Event:
        self.registry.register_product(product_name, formulation, ingredient_ids)
        return self.events.append(
            "INGREDIENT_MAPPED",
            "medicine_ingredient",
            product_name,
            1,
            f"登记商品 {product_name} 配方 {formulation} 的成分构成",
            {"formulation": formulation, "ingredient_ids": ingredient_ids},
        )

    def register_component(self, component: FoodComponent) -> None:
        self._components[component.component_id] = component

    # ---- 证据 ----

    def review_evidence(self, evidence: EvidenceStatement) -> Event:
        self._evidence[evidence.evidence_id] = evidence
        return self.events.append(
            "EVIDENCE_REVIEWED",
            "evidence_statement",
            evidence.evidence_id,
            evidence.version,
            f"审阅证据 {evidence.evidence_id}（{evidence.level.value}）：{evidence.finding}",
            {"source": evidence.source, "applicability": evidence.applicability},
        )

    def update_evidence(
        self,
        evidence_id: str,
        *,
        finding: str,
        source: str,
        applicability: str,
        reviewer: str,
        valid_until: str,
        revised_texts: dict[str, str] | None = None,
    ) -> tuple[EvidenceStatement, tuple[GuidanceVersion, ...]]:
        """证据更新：产生新证据版本，引用它的提示按影响范围换版。

        只有实际承载受影响提示的渠道（海报、药房屏幕、线上问答）换版；
        新提示版本需重新通过措辞与证据等级检查。
        """
        previous = self._evidence[evidence_id]
        updated = EvidenceStatement(
            evidence_id=evidence_id,
            component_id=previous.component_id,
            ingredient_id=previous.ingredient_id,
            level=previous.level,
            finding=finding,
            source=source,
            applicability=applicability,
            risk_populations=previous.risk_populations,
            pathway=previous.pathway,
            version=previous.version + 1,
            supersedes=evidence_id,
        )
        self._evidence[evidence_id] = updated
        self.events.append(
            "EVIDENCE_REVIEWED",
            "evidence_statement",
            evidence_id,
            updated.version,
            f"证据 {evidence_id} 更新为第 {updated.version} 版：{finding}",
            {"source": source, "applicability": applicability},
        )

        renewed = []
        for guidance in list(self._guidance.values()):
            if evidence_id not in guidance.evidence_ids:
                continue
            text = (revised_texts or {}).get(guidance.guidance_id, guidance.text)
            new_version = self._approve(
                guidance.guidance_id,
                guidance.content_type,
                guidance.certainty,
                text,
                guidance.evidence_ids,
                reviewer,
                self._clock(),
                valid_until,
                guidance.risk_populations,
            )
            self.channels.rollover(new_version, self._clock())
            renewed.append(new_version)
        return updated, tuple(renewed)

    # ---- 提示审校 ----

    def approve_guidance(
        self,
        guidance_id: str,
        content_type: ContentType,
        text: str,
        evidence_ids: tuple[str, ...],
        reviewer: str,
        valid_from: str,
        valid_until: str,
        risk_populations: tuple[str, ...] = (),
        certainty: Certainty = Certainty.CONFIRMED,
    ) -> GuidanceVersion:
        return self._approve(
            guidance_id,
            content_type,
            certainty,
            text,
            evidence_ids,
            reviewer,
            valid_from,
            valid_until,
            risk_populations,
        )

    def _approve(self, guidance_id, content_type, certainty, text, evidence_ids,
                 reviewer, valid_from, valid_until, risk_populations) -> GuidanceVersion:
        if not reviewer.strip():
            raise ValueError("必须登记审校人")
        if not valid_until or valid_until <= valid_from:
            raise ValueError("有效期必须晚于生效时间")
        violations = check_wording(text)
        if violations:
            raise ValueError("措辞未通过审校：" + "；".join(violations))
        evidence = tuple(self._evidence[eid] for eid in evidence_ids)
        if (
            content_type == ContentType.MEDICATION_SAFETY
            and certainty == Certainty.CONFIRMED
            and not all(supports_patient_safety_advice(item) for item in evidence)
        ):
            raise ValueError("细胞或动物研究证据不能支撑确定性的用药安全提示")
        previous = self._guidance.get(guidance_id)
        version = GuidanceVersion(
            guidance_id=guidance_id,
            version=previous.version + 1 if previous else 1,
            content_type=content_type,
            certainty=certainty,
            text=text,
            evidence_ids=tuple(evidence_ids),
            reviewer=reviewer,
            valid_from=valid_from,
            valid_until=valid_until,
            risk_populations=tuple(risk_populations),
            supersedes=f"{guidance_id}:{previous.version}" if previous else None,
        )
        self._guidance[guidance_id] = version
        self.events.append(
            "GUIDANCE_APPROVED",
            "guidance_version",
            guidance_id,
            version.version,
            f"提示 {guidance_id} 第 {version.version} 版经 {reviewer} 审校通过",
            {"content_type": content_type.value, "valid_until": valid_until},
        )
        return version

    # ---- 发布与送达 ----

    def publish(self, guidance_id: str, channels: list[Channel]) -> None:
        guidance = self._guidance[guidance_id]
        self.channels.publish(guidance, channels, self._clock())
        for channel in channels:
            self.events.append(
                "CHANNEL_UPDATED",
                "guidance_version",
                guidance_id,
                guidance.version,
                f"提示 {guidance_id} 第 {guidance.version} 版发布到 {channel.value}",
            )

    def deliver(self, receipt_id: str, guidance_id: str) -> PatientReceipt:
        return self.channels.deliver(receipt_id, self._guidance[guidance_id], self._clock())

    # ---- 更正 ----

    def correct(self, guidance_id: str, correction: str) -> int:
        """向所有曾收到该提示的患者追加更正，保留当时版本，返回影响条数。"""
        receipts = self.channels.receipts_for(guidance_id)
        for receipt in receipts:
            self.channels.append_correction(receipt.receipt_id, correction)
            self.events.append(
                "NOTICE_CORRECTED",
                "guidance_version",
                guidance_id,
                self._guidance[guidance_id].version,
                f"向送达记录 {receipt.receipt_id} 追加更正：{correction}",
            )
        return len(receipts)

    # ---- 查询与追溯 ----

    def answer(self, query: MedicationQuery) -> PatientAnswer:
        """面向患者的答复：成分无法确认时只表达不确定并引导咨询。"""
        if not query.ingredient_ids:
            return PatientAnswer((), True, UNCERTAIN_TEXT)
        items = []
        for guidance in self._guidance.values():
            linked = [self._evidence[eid] for eid in guidance.evidence_ids]
            if any(item.ingredient_id in query.ingredient_ids for item in linked):
                items.append(patient_view(guidance))
        if not items:
            return PatientAnswer((), True, UNCERTAIN_TEXT)
        return PatientAnswer(tuple(items), False, "")

    def trace(self, guidance_id: str) -> dict:
        """药师追溯：从提示追到证据、来源文献、适用对象与审校人。"""
        guidance = self._guidance[guidance_id]
        evidence = tuple(self._evidence[eid] for eid in guidance.evidence_ids)
        return pharmacist_trace(guidance, evidence)
