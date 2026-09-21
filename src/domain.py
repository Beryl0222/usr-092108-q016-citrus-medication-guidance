"""领域模型：柑橘活性成分、药物成分、相互作用证据、风险人群与提示版本。

所有实体均为不可变记录；业务更正通过产生后继版本表达，不改写历史。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class EvidenceLevel(str, Enum):
    """证据等级：人体证据方可支撑确定性措辞。"""

    HUMAN_CLINICAL = "人体临床研究"
    HUMAN_PK = "人体药动学研究"
    CASE_REPORT = "病例报告"
    ANIMAL = "动物研究"
    IN_VITRO = "体外或细胞研究"


HUMAN_LEVELS = frozenset(
    {EvidenceLevel.HUMAN_CLINICAL, EvidenceLevel.HUMAN_PK, EvidenceLevel.CASE_REPORT}
)


class EvidenceStatus(str, Enum):
    ACTIVE = "现行"
    SUPERSEDED = "已被新版替代"
    RETIRED = "已废止"


class GuidanceKind(str, Enum):
    """患者视图按此区分用药安全建议与一般营养知识。"""

    MEDICATION_SAFETY = "用药安全建议"
    GENERAL_NUTRITION = "一般营养知识"


class GuidanceStatus(str, Enum):
    APPROVED = "已审校发布"
    SUPERSEDED = "已被新版替代"
    WITHDRAWN = "已撤回"


class Audience(str, Enum):
    PATIENT = "患者"
    PHARMACIST = "药师"


class Channel(str, Enum):
    POSTER = "海报"
    PHARMACY_SCREEN = "药房屏幕"
    ONLINE_QA = "线上问答"


@dataclass(frozen=True)
class CitrusComponent:
    """柑橘活性成分，如呋喃香豆素类。"""

    component_id: str
    name: str
    mechanism: str = ""


@dataclass(frozen=True)
class CitrusExposure:
    """品种 + 加工形态归一后的柑橘暴露档案。"""

    exposure_id: str
    variety: str
    form: str
    component_ids: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class MedicineIngredient:
    """归一后的药物通用成分及其代谢途径。"""

    ingredient_id: str
    generic_name: str
    aliases: tuple[str, ...] = ()
    pathways: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductFormula:
    """商品配方版本：换配方必须留痕，按生效时间取用。"""

    product_name: str
    formula_version: int
    ingredient_ids: tuple[str, ...]
    effective_from: date
    note: str = ""


@dataclass(frozen=True)
class LiteratureRef:
    """来源文献。verified=False 表示联调示例引文，发布前须由审校人核实。"""

    ref_id: str
    citation: str
    verified: bool = False


@dataclass(frozen=True)
class EvidenceStatement:
    """相互作用证据：等级、效应、适用边界、文献、审校与有效期。"""

    evidence_id: str
    version: int
    component_id: str
    ingredient_id: str
    level: EvidenceLevel
    effect: str
    applicability: str
    literature: tuple[LiteratureRef, ...] = ()
    reviewed_by: str = ""
    reviewed_at: datetime | None = None
    valid_until: date | None = None
    status: EvidenceStatus = EvidenceStatus.ACTIVE


@dataclass(frozen=True)
class RiskPopulation:
    """风险人群，即提示的适用对象。"""

    population_id: str
    label: str
    note: str = ""


@dataclass(frozen=True)
class GuidanceVersion:
    """建议措辞版本：可追溯到证据、适用人群、审校人与有效期。"""

    guidance_id: str
    version: int
    kind: GuidanceKind
    audience: Audience
    text: str
    evidence_ids: tuple[str, ...] = ()
    population_ids: tuple[str, ...] = ()
    exposure_ids: tuple[str, ...] = ()
    reviewed_by: str = ""
    approved_at: datetime | None = None
    valid_until: date | None = None
    status: GuidanceStatus = GuidanceStatus.APPROVED
