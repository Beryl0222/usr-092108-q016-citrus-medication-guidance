"""领域模型：柑橘活性成分、药物成分与代谢途径、相互作用证据、提示版本。

所有记录一经登记不原地改写；证据或措辞变化一律产生新的版本记录。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EvidenceLevel(str, Enum):
    """证据等级：决定一条证据能支撑到哪一类结论。"""

    HUMAN_CLINICAL = "human_clinical"      # 人体临床研究
    HUMAN_CASE = "human_case"              # 人体个案报告
    ANIMAL = "animal"                      # 动物研究
    IN_VITRO = "in_vitro"                  # 细胞或体外研究
    EXPERT_CONSENSUS = "expert_consensus"  # 专家共识


# 只有这些等级的证据，才允许支撑面向患者的确定性用药安全提示。
# 细胞或动物研究只能表述为“证据有限”，不得写成个人停药或调整依据。
PATIENT_ACTIONABLE_LEVELS = frozenset(
    {
        EvidenceLevel.HUMAN_CLINICAL,
        EvidenceLevel.HUMAN_CASE,
        EvidenceLevel.EXPERT_CONSENSUS,
    }
)


class ContentType(str, Enum):
    """内容类型：让患者分清一般营养知识与用药安全建议。"""

    NUTRITION_GENERAL = "nutrition_general"    # 一般营养知识
    MEDICATION_SAFETY = "medication_safety"    # 用药安全建议


class Certainty(str, Enum):
    """结论的确定程度：无法确认的配方或用药信息一律为 UNCERTAIN。"""

    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class FoodComponent:
    """柑橘活性成分及其来源的水果品种与加工形态。"""

    component_id: str
    name: str
    source_forms: tuple[str, ...]  # 加工形态，如 鲜果、果汁、提取物
    note: str = ""


@dataclass(frozen=True)
class MedicineIngredient:
    """药物有效成分、别名与代谢途径；复方记录其组成成分。"""

    ingredient_id: str
    name: str
    aliases: tuple[str, ...] = ()
    metabolic_pathways: tuple[str, ...] = ()  # 如 CYP3A4、OATP1A2
    compound_parts: tuple[str, ...] = ()      # 复方组成成分的 ingredient_id

    @property
    def is_compound(self) -> bool:
        return bool(self.compound_parts)


@dataclass(frozen=True)
class EvidenceStatement:
    """一条相互作用证据：结论、来源文献与适用边界（剂量、形态、人群）。"""

    evidence_id: str
    component_id: str
    ingredient_id: str
    level: EvidenceLevel
    finding: str
    source: str                             # 来源文献
    applicability: str                      # 适用边界：剂量、形态、人群
    risk_populations: tuple[str, ...] = ()
    pathway: str | None = None              # 涉及的代谢途径
    version: int = 1
    supersedes: str | None = None           # 被替代的证据版本标识


@dataclass(frozen=True)
class GuidanceVersion:
    """一条提示的某个版本：措辞、证据链、审校人与有效期。"""

    guidance_id: str
    version: int
    content_type: ContentType
    certainty: Certainty
    text: str
    evidence_ids: tuple[str, ...]
    reviewer: str                           # 审校人
    valid_from: str
    valid_until: str                        # 有效期
    risk_populations: tuple[str, ...] = ()
    supersedes: str | None = None           # 前一版的 guidance_id:version
