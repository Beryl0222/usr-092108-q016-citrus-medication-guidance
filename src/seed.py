"""载入联调种子数据（data/seed.json）。

种子中的文献为示例引文（verified=False），正式发布前须由审校人核实。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .domain import (
    Audience,
    CitrusComponent,
    CitrusExposure,
    EvidenceLevel,
    EvidenceStatement,
    GuidanceKind,
    LiteratureRef,
    MedicineIngredient,
    ProductFormula,
    RiskPopulation,
)
from .service import AdvisoryCenter


def load_seed(center: AdvisoryCenter, data: dict) -> None:
    for record in data.get("components", []):
        center.citrus.register_component(
            CitrusComponent(record["component_id"], record["name"], record.get("mechanism", ""))
        )
    for record in data.get("exposures", []):
        center.citrus.register_exposure(
            CitrusExposure(
                record["exposure_id"],
                record["variety"],
                record["form"],
                tuple(record.get("component_ids", ())),
                record.get("note", ""),
            ),
            variety_aliases=tuple(record.get("variety_aliases", ())),
            form_aliases=tuple(record.get("form_aliases", ())),
        )
    for record in data.get("ingredients", []):
        center.medicines.register_ingredient(
            MedicineIngredient(
                record["ingredient_id"],
                record["generic_name"],
                tuple(record.get("aliases", ())),
                tuple(record.get("pathways", ())),
            )
        )
    for record in data.get("products", []):
        center.medicines.register_formula(
            ProductFormula(
                record["product_name"],
                record["formula_version"],
                tuple(record["ingredient_ids"]),
                date.fromisoformat(record["effective_from"]),
                record.get("note", ""),
            )
        )
    for record in data.get("populations", []):
        center.guidance.register_population(
            RiskPopulation(record["population_id"], record["label"], record.get("note", ""))
        )
    for record in data.get("evidence", []):
        center.evidence.register(
            EvidenceStatement(
                evidence_id=record["evidence_id"],
                version=1,
                component_id=record["component_id"],
                ingredient_id=record["ingredient_id"],
                level=EvidenceLevel[record["level"]],
                effect=record["effect"],
                applicability=record["applicability"],
                literature=tuple(
                    LiteratureRef(item["ref_id"], item["citation"], item.get("verified", False))
                    for item in record.get("literature", [])
                ),
                reviewed_by=record["reviewed_by"],
                reviewed_at=datetime.fromisoformat(record["reviewed_at"]),
                valid_until=date.fromisoformat(record["valid_until"]),
            )
        )
    for record in data.get("guidance", []):
        center.guidance.approve(
            guidance_id=record["guidance_id"],
            kind=GuidanceKind[record["kind"]],
            audience=Audience[record["audience"]],
            text=record["text"],
            evidence_ids=tuple(record.get("evidence_ids", ())),
            population_ids=tuple(record.get("population_ids", ())),
            exposure_ids=tuple(record.get("exposure_ids", ())),
            reviewed_by=record["reviewed_by"],
            approved_at=datetime.fromisoformat(record["approved_at"]),
            valid_until=date.fromisoformat(record["valid_until"]),
        )


def load_seed_file(center: AdvisoryCenter, path: str | Path) -> None:
    load_seed(center, json.loads(Path(path).read_text(encoding="utf-8")))
