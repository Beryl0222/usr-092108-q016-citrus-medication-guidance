"""测试共用的服务装配。"""

from src.models import (
    ContentType,
    EvidenceLevel,
    EvidenceStatement,
    FoodComponent,
    MedicineIngredient,
)
from src.service import GuidanceService

CLOCK = "2026-09-21T09:00:00+08:00"
VALID_FROM = "2026-09-21"
VALID_UNTIL = "2027-09-21"


def build_service() -> GuidanceService:
    service = GuidanceService(clock=lambda: CLOCK)
    service.register_component(
        FoodComponent("fc-fcn", "呋喃香豆素", ("西柚鲜果", "西柚汁", "提取物"))
    )
    service.register_ingredient(
        MedicineIngredient(
            "ing-sim", "辛伐他汀", aliases=("舒降之",), metabolic_pathways=("CYP3A4",)
        )
    )
    service.register_ingredient(
        MedicineIngredient("ing-aml", "氨氯地平", metabolic_pathways=("CYP3A4",))
    )
    service.register_product("某品牌降脂胶囊", "2025版", ("ing-sim",))
    service.review_evidence(
        EvidenceStatement(
            evidence_id="ev-1",
            component_id="fc-fcn",
            ingredient_id="ing-sim",
            level=EvidenceLevel.HUMAN_CLINICAL,
            finding="西柚汁抑制 CYP3A4，使辛伐他汀血药浓度升高",
            source="某临床药理研究（人体）",
            applicability="每日饮用 200ml 以上西柚汁；不适用于偶尔食用少量鲜果",
            risk_populations=("老年人", "肝功能不全者"),
            pathway="CYP3A4",
        )
    )
    service.review_evidence(
        EvidenceStatement(
            evidence_id="ev-2",
            component_id="fc-fcn",
            ingredient_id="ing-aml",
            level=EvidenceLevel.IN_VITRO,
            finding="细胞实验提示呋喃香豆素可能影响氨氯地平代谢",
            source="某体外实验",
            applicability="细胞体系，尚无人体数据",
        )
    )
    return service


def approve_safety_guidance(service: GuidanceService, guidance_id: str = "g-1"):
    return service.approve_guidance(
        guidance_id,
        ContentType.MEDICATION_SAFETY,
        "服用辛伐他汀期间应避免大量饮用西柚汁，具体请咨询医生或药师。",
        ("ev-1",),
        reviewer="药师甲",
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        risk_populations=("老年人", "肝功能不全者"),
    )
