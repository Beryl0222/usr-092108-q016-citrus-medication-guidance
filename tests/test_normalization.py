import unittest

from src.models import Certainty, MedicineIngredient
from src.normalization import IngredientRegistry


def build_registry() -> IngredientRegistry:
    registry = IngredientRegistry()
    registry.register_ingredient(
        MedicineIngredient("ing-sim", "辛伐他汀", aliases=("舒降之",), metabolic_pathways=("CYP3A4",))
    )
    registry.register_ingredient(MedicineIngredient("ing-a", "成分甲"))
    registry.register_ingredient(MedicineIngredient("ing-b", "成分乙"))
    registry.register_ingredient(
        MedicineIngredient("ing-comp", "复方降压片", compound_parts=("ing-a", "ing-b"))
    )
    registry.register_product("某品牌胶囊", "2025版", ("ing-sim",))
    return registry


class NormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_registry()

    def test_alias_resolves_to_ingredient(self) -> None:
        result = self.registry.normalize("舒降之")
        self.assertEqual(result.certainty, Certainty.CONFIRMED)
        self.assertEqual(result.ingredient_ids, ("ing-sim",))

    def test_compound_expands_to_parts(self) -> None:
        result = self.registry.normalize("复方降压片")
        self.assertEqual(result.ingredient_ids, ("ing-a", "ing-b"))

    def test_product_with_registered_formulation(self) -> None:
        result = self.registry.normalize("某品牌胶囊", "2025版")
        self.assertEqual(result.certainty, Certainty.CONFIRMED)
        self.assertEqual(result.ingredient_ids, ("ing-sim",))

    def test_product_with_unknown_formulation_is_uncertain(self) -> None:
        # 商品换配方后不得沿用旧配方猜测成分
        for formulation in (None, "2026版"):
            result = self.registry.normalize("某品牌胶囊", formulation)
            self.assertEqual(result.certainty, Certainty.UNCERTAIN)
            self.assertEqual(result.ingredient_ids, ())

    def test_unknown_name_is_uncertain(self) -> None:
        result = self.registry.normalize("网络文章里的神奇保健品")
        self.assertEqual(result.certainty, Certainty.UNCERTAIN)
        self.assertEqual(result.ingredient_ids, ())


if __name__ == "__main__":
    unittest.main()
