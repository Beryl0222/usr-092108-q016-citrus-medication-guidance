"""最小必要查询与角色视图。

查询只使用完成判断所需的最少用药信息：归一后的成分标识与必要的人群
信息，不携带病历、诊断或身份信息；员工看不到完整病历。药师可以从
每条提示追到证据和适用对象，患者视图则标明内容类型。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import EvidenceStatement, GuidanceVersion
from .normalization import IngredientRegistry, NormalizationResult


class Role(str, Enum):
    STAFF = "staff"            # 员工：只看完成职责所必需的字段
    PHARMACIST = "pharmacist"  # 药师：可追到证据与适用对象


@dataclass(frozen=True)
class MedicationQuery:
    """归一后的最小查询：只有成分标识与必要的人群信息。"""

    ingredient_ids: tuple[str, ...]
    risk_population: str | None = None


def build_query(
    items: list[tuple[str, str | None]],
    registry: IngredientRegistry,
    risk_population: str | None = None,
) -> tuple[MedicationQuery, tuple[NormalizationResult, ...]]:
    """把（名称, 配方版本）列表归一为最小查询。

    无法确认的条目不会进入查询，只体现在归一结果里，由上层引导咨询。
    """
    results: list[NormalizationResult] = []
    confirmed: list[str] = []
    for name, formulation in items:
        result = registry.normalize(name, formulation)
        results.append(result)
        for ingredient_id in result.ingredient_ids:
            if ingredient_id not in confirmed:
                confirmed.append(ingredient_id)
    return MedicationQuery(tuple(confirmed), risk_population), tuple(results)


def patient_view(guidance: GuidanceVersion) -> dict:
    """患者视图：标明内容类型，分清一般营养知识与用药安全建议。"""
    return {
        "content_type": guidance.content_type.value,
        "certainty": guidance.certainty.value,
        "text": guidance.text,
        "valid_until": guidance.valid_until,
    }


def pharmacist_trace(
    guidance: GuidanceVersion, evidence: tuple[EvidenceStatement, ...]
) -> dict:
    """药师追溯视图：从提示追到证据、来源文献、适用对象与审校人。"""
    return {
        "guidance_id": guidance.guidance_id,
        "version": guidance.version,
        "content_type": guidance.content_type.value,
        "reviewer": guidance.reviewer,
        "valid_from": guidance.valid_from,
        "valid_until": guidance.valid_until,
        "risk_populations": guidance.risk_populations,
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "level": item.level.value,
                "finding": item.finding,
                "source": item.source,
                "applicability": item.applicability,
                "risk_populations": item.risk_populations,
                "pathway": item.pathway,
            }
            for item in evidence
        ],
    }
