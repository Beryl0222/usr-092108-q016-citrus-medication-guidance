"""商品名、药品别名与复方组成的归一。

规则：商品换配方、药品别名和复方组成必须先归一，再进入证据匹配；
任何无法确认的配方都返回不确定结果，绝不猜测成分。
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Certainty, MedicineIngredient


@dataclass(frozen=True)
class NormalizationResult:
    certainty: Certainty
    ingredient_ids: tuple[str, ...]
    note: str


class IngredientRegistry:
    """有效成分、别名、复方组成与商品配方版本的登记处。"""

    def __init__(self) -> None:
        self._ingredients: dict[str, MedicineIngredient] = {}
        self._alias: dict[str, str] = {}
        # 商品名 -> {配方版本 -> 成分标识}
        self._products: dict[str, dict[str, tuple[str, ...]]] = {}

    def register_ingredient(self, ingredient: MedicineIngredient) -> None:
        self._ingredients[ingredient.ingredient_id] = ingredient
        self._alias[ingredient.name] = ingredient.ingredient_id
        for alias in ingredient.aliases:
            self._alias[alias] = ingredient.ingredient_id

    def register_product(
        self, product_name: str, formulation: str, ingredient_ids: tuple[str, ...]
    ) -> None:
        """登记某个商品在指定配方版本下的成分构成。"""
        for ingredient_id in ingredient_ids:
            if ingredient_id not in self._ingredients:
                raise KeyError(f"未登记的成分：{ingredient_id}")
        self._products.setdefault(product_name, {})[formulation] = tuple(ingredient_ids)

    def get(self, ingredient_id: str) -> MedicineIngredient:
        return self._ingredients[ingredient_id]

    def normalize(self, name: str, formulation: str | None = None) -> NormalizationResult:
        """把商品名、别名或复方名归一到有效成分标识。"""
        key = name.strip()
        if key in self._products:
            versions = self._products[key]
            if formulation and formulation in versions:
                return self._expand(
                    versions[formulation], f"商品 {key}（配方 {formulation}）已归一"
                )
            # 商品存在但配方未知或未登记：不得沿用旧配方猜测成分
            return NormalizationResult(
                Certainty.UNCERTAIN,
                (),
                f"商品 {key} 的配方无法确认，需提供配方版本后再判断",
            )
        ingredient_id = self._alias.get(key)
        if ingredient_id is None and key in self._ingredients:
            ingredient_id = key
        if ingredient_id is None:
            return NormalizationResult(
                Certainty.UNCERTAIN, (), f"无法确认 {key} 的有效成分"
            )
        return self._expand((ingredient_id,), f"{key} 已归一")

    def _expand(self, ingredient_ids: tuple[str, ...], note: str) -> NormalizationResult:
        """展开复方组成，只保留有效成分。"""
        expanded: list[str] = []

        def visit(ingredient_id: str) -> None:
            ingredient = self._ingredients[ingredient_id]
            if ingredient.is_compound:
                for part in ingredient.compound_parts:
                    visit(part)
            elif ingredient_id not in expanded:
                expanded.append(ingredient_id)

        for item in ingredient_ids:
            visit(item)
        return NormalizationResult(Certainty.CONFIRMED, tuple(expanded), note)
