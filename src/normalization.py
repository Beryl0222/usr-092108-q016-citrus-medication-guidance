"""名称归一：商品名/别名/复方组成/换配方 → 通用成分；品种+加工形态 → 柑橘暴露。

无法确认的输入绝不猜测，返回不确定结果并引导咨询。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

from .domain import CitrusComponent, CitrusExposure, MedicineIngredient, ProductFormula
from .events import EventLog

CONSULT_HINT = "请核对药品通用名，或咨询医生、药师后再作判断。"


class NormalizationStatus(str, Enum):
    CONFIRMED = "已确认"
    AMBIGUOUS = "待澄清"
    UNKNOWN = "无法确认"


@dataclass(frozen=True)
class NormalizedMedication:
    status: NormalizationStatus
    ingredient_ids: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class NormalizedExposure:
    status: NormalizationStatus
    exposure: CitrusExposure | None = None
    message: str = ""


def _event_time(at: datetime | date | None) -> datetime:
    return at if isinstance(at, datetime) else datetime.now(timezone.utc)


class MedicineNormalizer:
    """药品名称归一。商品换配方以配方版本留痕，按时间取用。"""

    def __init__(self, log: EventLog | None = None) -> None:
        self._ingredients: dict[str, MedicineIngredient] = {}
        self._name_index: dict[str, set[str]] = {}
        self._formulas: dict[str, list[ProductFormula]] = {}
        self._log = log

    def register_ingredient(self, ingredient: MedicineIngredient) -> None:
        self._ingredients[ingredient.ingredient_id] = ingredient
        for name in (ingredient.generic_name, *ingredient.aliases):
            self._name_index.setdefault(name.strip(), set()).add(ingredient.ingredient_id)

    def register_formula(self, formula: ProductFormula) -> None:
        history = self._formulas.setdefault(formula.product_name.strip(), [])
        expected = len(history) + 1
        if formula.formula_version != expected:
            raise ValueError(f"配方版本必须连续：{formula.product_name} 期望 v{expected}")
        unknown = [iid for iid in formula.ingredient_ids if iid not in self._ingredients]
        if unknown:
            raise ValueError(f"配方引用了未登记的成分：{unknown}")
        history.append(formula)

    def formulas_of(self, product_name: str) -> tuple[ProductFormula, ...]:
        return tuple(self._formulas.get(product_name.strip(), ()))

    def normalize(self, name: str, *, at: datetime | date | None = None) -> NormalizedMedication:
        key = name.strip()
        if not key:
            return NormalizedMedication(
                NormalizationStatus.UNKNOWN, message=f"名称为空，无法归一。{CONSULT_HINT}"
            )
        name_hits = set(self._name_index.get(key, set()))
        formula = self._current_formula(key, at)
        if formula is None and not name_hits:
            return NormalizedMedication(
                NormalizationStatus.UNKNOWN,
                message=f"无法确认「{key}」对应的药品成分。{CONSULT_HINT}",
            )
        if formula is not None and not name_hits:
            self._emit(key, formula.ingredient_ids, at, formula.formula_version)
            return NormalizedMedication(NormalizationStatus.CONFIRMED, ingredient_ids=formula.ingredient_ids)
        if len(name_hits) == 1 and formula is None:
            ingredient_id = next(iter(name_hits))
            self._emit(key, (ingredient_id,), at, 1)
            return NormalizedMedication(NormalizationStatus.CONFIRMED, ingredient_ids=(ingredient_id,))
        candidates = tuple(sorted(name_hits | set(formula.ingredient_ids if formula else ())))
        return NormalizedMedication(
            NormalizationStatus.AMBIGUOUS,
            candidates=candidates,
            message=f"「{key}」可能对应多种成分（{', '.join(candidates)}），请进一步确认。{CONSULT_HINT}",
        )

    def _current_formula(self, product_name: str, at: datetime | date | None) -> ProductFormula | None:
        history = self._formulas.get(product_name)
        if not history:
            return None
        day = at.date() if isinstance(at, datetime) else (at or date.today())
        effective = [f for f in history if f.effective_from <= day]
        return effective[-1] if effective else None

    def _emit(
        self, source: str, ingredient_ids: tuple[str, ...], at: datetime | date | None, version: int
    ) -> None:
        if self._log is None:
            return
        for ingredient_id in ingredient_ids:
            generic = self._ingredients[ingredient_id].generic_name
            self._log.append(
                event_type="INGREDIENT_MAPPED",
                aggregate_type="medicine_ingredient",
                aggregate_id=ingredient_id,
                occurred_at=_event_time(at),
                version=version,
                summary=f"归一：{source} → {generic}",
            )


class CitrusNormalizer:
    """柑橘品种与加工形态归一。同一品种、不同加工形态，活性成分可能完全不同。"""

    def __init__(self, log: EventLog | None = None) -> None:
        self._components: dict[str, CitrusComponent] = {}
        self._exposures: dict[tuple[str, str], CitrusExposure] = {}
        self._variety_aliases: dict[str, str] = {}
        self._form_aliases: dict[str, str] = {}
        self._log = log

    def register_component(self, component: CitrusComponent) -> None:
        self._components[component.component_id] = component

    def component(self, component_id: str) -> CitrusComponent | None:
        return self._components.get(component_id)

    def register_exposure(
        self,
        exposure: CitrusExposure,
        *,
        variety_aliases: tuple[str, ...] = (),
        form_aliases: tuple[str, ...] = (),
    ) -> None:
        unknown = [cid for cid in exposure.component_ids if cid not in self._components]
        if unknown:
            raise ValueError(f"暴露档案引用了未登记的活性成分：{unknown}")
        self._exposures[(exposure.variety, exposure.form)] = exposure
        for alias in (exposure.variety, *variety_aliases):
            self._variety_aliases[alias.strip()] = exposure.variety
        for alias in (exposure.form, *form_aliases):
            self._form_aliases[alias.strip()] = exposure.form

    def normalize(
        self, variety: str, form: str, *, at: datetime | None = None
    ) -> NormalizedExposure:
        canonical_variety = self._variety_aliases.get(variety.strip())
        canonical_form = self._form_aliases.get(form.strip())
        exposure = (
            self._exposures.get((canonical_variety, canonical_form))
            if canonical_variety and canonical_form
            else None
        )
        if exposure is None:
            return NormalizedExposure(
                NormalizationStatus.UNKNOWN,
                message=(
                    f"无法确认「{variety}·{form}」的柑橘活性成分"
                    f"（品种或加工形态未登记）。请咨询药师或补充产品信息。"
                ),
            )
        if self._log is not None:
            self._log.append(
                event_type="INGREDIENT_MAPPED",
                aggregate_type="food_component",
                aggregate_id=exposure.exposure_id,
                occurred_at=_event_time(at),
                version=1,
                summary=f"归一：{variety}·{form} → {exposure.exposure_id}",
            )
        return NormalizedExposure(NormalizationStatus.CONFIRMED, exposure=exposure)
