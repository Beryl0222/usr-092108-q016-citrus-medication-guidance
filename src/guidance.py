"""建议措辞规则：审校前的措辞检查、证据等级约束与标准不确定表述。

服务绝不建议自行停药、换药，也不推断诊断；
无法确认的配方或用药信息一律表达不确定并引导咨询。
"""

from __future__ import annotations

from .models import PATIENT_ACTIONABLE_LEVELS, EvidenceLevel, EvidenceStatement

# 面向患者的提示中禁止出现的表述：指使停药、换药、调量或推断诊断。
FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "可以停药",
    "建议停药",
    "请停药",
    "停用",
    "换药",
    "改服",
    "改用",
    "换成",
    "减量服用",
    "加量服用",
    "诊断为",
    "确诊为",
    "您患有",
    "你患有",
)

CONSULT_GUIDANCE = "请咨询医生或药师，不要自行调整用药。"

# 无法确认配方或用药信息时的标准表述：表达不确定并引导咨询。
UNCERTAIN_TEXT = (
    "目前无法确认该商品配方或用药信息，现有资料不足以给出判断。" + CONSULT_GUIDANCE
)


def check_wording(text: str) -> list[str]:
    """审校前检查：返回所有违规措辞说明，空列表表示通过。"""
    return [f"含有禁止表述：{pattern}" for pattern in FORBIDDEN_PATTERNS if pattern in text]


def limited_evidence_text(level: EvidenceLevel) -> str:
    """细胞或动物研究只能表述为证据有限，不得写成个人用药调整依据。"""
    label = {
        EvidenceLevel.IN_VITRO: "细胞或体外研究",
        EvidenceLevel.ANIMAL: "动物研究",
    }[level]
    return f"现有证据仅来自{label}，尚不能作为个人用药调整的依据。" + CONSULT_GUIDANCE


def supports_patient_safety_advice(evidence: EvidenceStatement) -> bool:
    """该证据是否足以支撑面向患者的确定性用药安全提示。"""
    return evidence.level in PATIENT_ACTIONABLE_LEVELS
