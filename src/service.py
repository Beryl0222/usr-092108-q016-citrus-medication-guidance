"""门面：把归一、证据、措辞、发布与查询串成一次咨询。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from .evidence import EvidenceRegistry, EvidenceStatement
from .events import EventLog
from .guidance import GuidanceService
from .normalization import CitrusNormalizer, MedicineNormalizer, NormalizationStatus
from .publishing import ImpactReport, Publisher
from .query import AdviceItem, MinimalMedicationQuery, query_advice


@dataclass(frozen=True)
class ConsultResult:
    """一次咨询的结果：命中的提示与无法确认事项（含咨询引导）。"""

    items: tuple[AdviceItem, ...]
    uncertainties: tuple[str, ...]


class AdvisoryCenter:
    """区域药学中心的食物与用药提示发布服务。"""

    def __init__(self) -> None:
        self.log = EventLog()
        self.medicines = MedicineNormalizer(self.log)
        self.citrus = CitrusNormalizer(self.log)
        self.evidence = EvidenceRegistry(self.log)
        self.guidance = GuidanceService(self.evidence, log=self.log)
        self.publisher = Publisher(self.guidance, log=self.log)

    def consult(
        self,
        *,
        medication_names: Iterable[str] = (),
        variety: str | None = None,
        form: str | None = None,
    ) -> ConsultResult:
        """先归一，再用最少信息查询。无法确认的输入表达不确定性并引导咨询。"""
        uncertainties: list[str] = []
        ingredient_ids: list[str] = []
        for name in medication_names:
            result = self.medicines.normalize(name)
            if result.status is NormalizationStatus.CONFIRMED:
                ingredient_ids.extend(result.ingredient_ids)
            else:
                uncertainties.append(result.message)
        exposure_id: str | None = None
        component_ids: tuple[str, ...] = ()
        if (variety is None) != (form is None):
            uncertainties.append("请同时提供柑橘的品种与加工形态，以便判断活性成分。")
        elif variety is not None and form is not None:
            result = self.citrus.normalize(variety, form)
            if result.status is NormalizationStatus.CONFIRMED and result.exposure is not None:
                exposure_id = result.exposure.exposure_id
                component_ids = result.exposure.component_ids
            else:
                uncertainties.append(result.message)
        query = MinimalMedicationQuery(
            tuple(dict.fromkeys(ingredient_ids)), exposure_id, component_ids
        )
        items = query_advice(query, guidance=self.guidance, evidence=self.evidence)
        return ConsultResult(tuple(items), tuple(uncertainties))

    def update_evidence(
        self,
        evidence_id: str,
        *,
        reviewed_by: str,
        reviewed_at: datetime,
        valid_until: date,
        **fields,
    ) -> tuple[EvidenceStatement, tuple[str, ...]]:
        """更新证据并返回受影响提示编号，供修订措辞与换版使用。"""
        new_version = self.evidence.update(
            evidence_id,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            valid_until=valid_until,
            **fields,
        )
        affected = tuple(
            sorted({g.guidance_id for g in self.guidance.find_by_evidence(evidence_id)})
        )
        return new_version, affected

    def reversion_channels(
        self, affected_guidance_ids: Iterable[str], *, at: datetime, reason: str
    ) -> ImpactReport:
        """按影响范围为渠道换版；未受影响的渠道保持原版本。"""
        return self.publisher.reevaluate(affected_guidance_ids, at=at, reason=reason)
