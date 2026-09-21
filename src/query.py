"""最少信息查询与分角色视图。

查询只接受归一后的成分与柑橘暴露标识，不接收身份、诊断或病历信息；
员工视图同样不含任何病历字段。药师可从每条提示追溯到证据与适用对象。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .domain import Audience, EvidenceStatus, GuidanceKind, GuidanceVersion
from .evidence import EvidenceRegistry
from .guidance import GuidanceService


@dataclass(frozen=True)
class MinimalMedicationQuery:
    """完成判断所需的最少用药信息：仅归一后的成分与柑橘暴露。"""

    ingredient_ids: tuple[str, ...] = ()
    exposure_id: str | None = None
    exposure_component_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdviceItem:
    guidance_id: str
    version: int
    kind: GuidanceKind
    audience: Audience
    text: str
    valid_until: date | None


def query_advice(
    query: MinimalMedicationQuery,
    *,
    guidance: GuidanceService,
    evidence: EvidenceRegistry,
) -> list[AdviceItem]:
    items: list[AdviceItem] = []
    ingredients = set(query.ingredient_ids)
    components = set(query.exposure_component_ids)
    for version in guidance.approved():
        if _matches(version, query, ingredients, components, evidence):
            items.append(
                AdviceItem(
                    version.guidance_id,
                    version.version,
                    version.kind,
                    version.audience,
                    version.text,
                    version.valid_until,
                )
            )
    return items


def _matches(
    version: GuidanceVersion,
    query: MinimalMedicationQuery,
    ingredients: set[str],
    components: set[str],
    evidence: EvidenceRegistry,
) -> bool:
    if version.kind is GuidanceKind.GENERAL_NUTRITION:
        return query.exposure_id is not None and query.exposure_id in version.exposure_ids
    if not ingredients or not components:
        return False
    for evidence_id in version.evidence_ids:
        statement = evidence.current(evidence_id)
        if statement is None or statement.status is not EvidenceStatus.ACTIVE:
            continue
        if statement.ingredient_id in ingredients and statement.component_id in components:
            return True
    return False


def patient_view(
    items: list[AdviceItem] | tuple[AdviceItem, ...],
    *,
    uncertainties: tuple[str, ...] = (),
) -> dict:
    """患者视图：明确区分用药安全建议与一般营养知识，并呈现不确定信息。"""

    def public(item: AdviceItem) -> dict:
        return {
            "guidance_id": item.guidance_id,
            "version": item.version,
            "text": item.text,
            "valid_until": item.valid_until.isoformat() if item.valid_until else None,
        }

    patient_items = [i for i in items if i.audience is Audience.PATIENT]
    return {
        "medication_safety": {
            "label": GuidanceKind.MEDICATION_SAFETY.value,
            "items": [
                public(i) for i in patient_items if i.kind is GuidanceKind.MEDICATION_SAFETY
            ],
        },
        "general_nutrition": {
            "label": GuidanceKind.GENERAL_NUTRITION.value,
            "items": [
                public(i) for i in patient_items if i.kind is GuidanceKind.GENERAL_NUTRITION
            ],
        },
        "uncertainties": list(uncertainties),
    }


def staff_view(
    items: list[AdviceItem] | tuple[AdviceItem, ...],
    *,
    guidance: GuidanceService,
    evidence: EvidenceRegistry,
) -> list[dict]:
    """员工视图：提示及其证据、适用人群。不含任何患者病历字段。"""
    view: list[dict] = []
    for item in items:
        version = guidance.get(item.guidance_id, item.version)
        if version is None:
            continue
        view.append(
            {
                "guidance_id": version.guidance_id,
                "version": version.version,
                "kind": version.kind.value,
                "audience": version.audience.value,
                "text": version.text,
                "reviewed_by": version.reviewed_by,
                "valid_until": version.valid_until.isoformat() if version.valid_until else None,
                "populations": [
                    population.label
                    for pid in version.population_ids
                    if (population := guidance.population(pid)) is not None
                ],
                "evidence": [
                    {
                        "evidence_id": statement.evidence_id,
                        "version": statement.version,
                        "level": statement.level.value,
                        "effect": statement.effect,
                        "applicability": statement.applicability,
                        "literature": [ref.citation for ref in statement.literature],
                    }
                    for eid in version.evidence_ids
                    if (statement := evidence.current(eid)) is not None
                ],
            }
        )
    return view


@dataclass(frozen=True)
class EvidenceTrace:
    evidence_id: str
    version: int
    level: str
    effect: str
    applicability: str
    literature: tuple[str, ...]
    reviewed_by: str
    valid_until: date | None


@dataclass(frozen=True)
class GuidanceTrace:
    """一条提示的完整追溯：措辞、审校、有效期、适用人群与证据链。"""

    guidance_id: str
    version: int
    kind: GuidanceKind
    text: str
    reviewed_by: str
    valid_until: date | None
    populations: tuple[str, ...]
    evidence: tuple[EvidenceTrace, ...]


def trace_guidance(
    guidance_id: str,
    *,
    guidance: GuidanceService,
    evidence: EvidenceRegistry,
) -> GuidanceTrace | None:
    version = guidance.latest(guidance_id)
    if version is None:
        return None
    populations = tuple(
        population.label
        for pid in version.population_ids
        if (population := guidance.population(pid)) is not None
    )
    statements: list[EvidenceTrace] = []
    for evidence_id in version.evidence_ids:
        statement = evidence.current(evidence_id)
        if statement is None:
            continue
        statements.append(
            EvidenceTrace(
                statement.evidence_id,
                statement.version,
                statement.level.value,
                statement.effect,
                statement.applicability,
                tuple(ref.citation for ref in statement.literature),
                statement.reviewed_by,
                statement.valid_until,
            )
        )
    return GuidanceTrace(
        version.guidance_id,
        version.version,
        version.kind,
        version.text,
        version.reviewed_by,
        version.valid_until,
        populations,
        tuple(statements),
    )
