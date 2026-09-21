import unittest
from datetime import date, datetime, timedelta, timezone

from src.domain import CitrusComponent, CitrusExposure, MedicineIngredient, ProductFormula
from src.events import EventLog
from src.normalization import CitrusNormalizer, MedicineNormalizer, NormalizationStatus

TZ = timezone(timedelta(hours=8))


def make_medicine_normalizer() -> tuple[MedicineNormalizer, EventLog]:
    log = EventLog()
    normalizer = MedicineNormalizer(log)
    normalizer.register_ingredient(
        MedicineIngredient("simvastatin", "辛伐他汀", ("舒降之", "辛可"), ("CYP3A4",))
    )
    normalizer.register_ingredient(
        MedicineIngredient("ezetimibe", "依折麦布", ("益适纯",), ("UGT",))
    )
    normalizer.register_formula(
        ProductFormula("葆至能", 1, ("ezetimibe", "simvastatin"), date(2024, 1, 1), "依折麦布辛伐他汀片")
    )
    normalizer.register_formula(
        ProductFormula("示例复方降脂胶囊", 1, ("simvastatin",), date(2024, 1, 1))
    )
    normalizer.register_formula(
        ProductFormula(
            "示例复方降脂胶囊", 2, ("simvastatin", "ezetimibe"), date(2026, 6, 1), "厂家换配方（示例）"
        )
    )
    return normalizer, log


class MedicineNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer, self.log = make_medicine_normalizer()

    def test_brand_alias_resolves_to_generic(self) -> None:
        result = self.normalizer.normalize("舒降之")
        self.assertEqual(result.status, NormalizationStatus.CONFIRMED)
        self.assertEqual(result.ingredient_ids, ("simvastatin",))
        self.assertEqual(len(self.log.of_type("INGREDIENT_MAPPED")), 1)

    def test_compound_product_expands_to_components(self) -> None:
        result = self.normalizer.normalize("葆至能")
        self.assertEqual(result.status, NormalizationStatus.CONFIRMED)
        self.assertEqual(set(result.ingredient_ids), {"ezetimibe", "simvastatin"})

    def test_reformulation_uses_formula_effective_at_time(self) -> None:
        before = self.normalizer.normalize(
            "示例复方降脂胶囊", at=datetime(2025, 1, 1, tzinfo=TZ)
        )
        self.assertEqual(before.ingredient_ids, ("simvastatin",))
        after = self.normalizer.normalize(
            "示例复方降脂胶囊", at=datetime(2026, 9, 1, tzinfo=TZ)
        )
        self.assertEqual(set(after.ingredient_ids), {"simvastatin", "ezetimibe"})
        self.assertEqual(len(self.normalizer.formulas_of("示例复方降脂胶囊")), 2)

    def test_unknown_name_expresses_uncertainty_and_guides_consult(self) -> None:
        result = self.normalizer.normalize("某进口胶囊")
        self.assertEqual(result.status, NormalizationStatus.UNKNOWN)
        self.assertIn("咨询", result.message)
        self.assertEqual(self.log.of_type("INGREDIENT_MAPPED"), [])

    def test_alias_collision_is_ambiguous(self) -> None:
        self.normalizer.register_ingredient(
            MedicineIngredient("other-statin", "某他汀", ("辛可",), ("CYP3A4",))
        )
        result = self.normalizer.normalize("辛可")
        self.assertEqual(result.status, NormalizationStatus.AMBIGUOUS)
        self.assertEqual(result.candidates, ("other-statin", "simvastatin"))
        self.assertIn("咨询", result.message)


def make_citrus_normalizer() -> tuple[CitrusNormalizer, EventLog]:
    log = EventLog()
    normalizer = CitrusNormalizer(log)
    normalizer.register_component(
        CitrusComponent("furanocoumarin", "呋喃香豆素类（佛手柑素等）", "不可逆抑制肠道CYP3A4")
    )
    normalizer.register_component(CitrusComponent("naringin", "柚皮苷"))
    normalizer.register_exposure(
        CitrusExposure("grapefruit-juice", "西柚", "果汁", ("furanocoumarin", "naringin")),
        variety_aliases=("葡萄柚",),
        form_aliases=("西柚汁", "鲜榨果汁"),
    )
    normalizer.register_exposure(
        CitrusExposure("grapefruit-flavor-drink", "西柚味饮料", "调配饮料", (), "香精调配，不含果汁"),
        variety_aliases=("西柚味汽水",),
        form_aliases=("香精饮料",),
    )
    return normalizer, log


class CitrusNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer, self.log = make_citrus_normalizer()

    def test_variety_and_form_aliases_resolve(self) -> None:
        result = self.normalizer.normalize("葡萄柚", "鲜榨果汁")
        self.assertEqual(result.status, NormalizationStatus.CONFIRMED)
        self.assertIsNotNone(result.exposure)
        self.assertEqual(result.exposure.exposure_id, "grapefruit-juice")
        self.assertEqual(
            self.log.of_type("INGREDIENT_MAPPED")[0].aggregate_type, "food_component"
        )

    def test_processing_form_changes_active_components(self) -> None:
        result = self.normalizer.normalize("西柚味汽水", "香精饮料")
        self.assertEqual(result.status, NormalizationStatus.CONFIRMED)
        self.assertEqual(result.exposure.component_ids, ())

    def test_unknown_variety_expresses_uncertainty(self) -> None:
        result = self.normalizer.normalize("某种杂交柑橘", "果汁")
        self.assertEqual(result.status, NormalizationStatus.UNKNOWN)
        self.assertIn("咨询", result.message)


if __name__ == "__main__":
    unittest.main()
