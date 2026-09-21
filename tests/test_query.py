import json
import unittest
from pathlib import Path

from src.query import MinimalMedicationQuery, patient_view, staff_view, trace_guidance
from src.seed import load_seed_file
from src.service import AdvisoryCenter

SEED = Path(__file__).parents[1] / "data" / "seed.json"


def make_center() -> AdvisoryCenter:
    center = AdvisoryCenter()
    load_seed_file(center, SEED)
    return center


class QueryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.center = make_center()

    def test_consult_grapefruit_juice_with_brand_name(self) -> None:
        result = self.center.consult(
            medication_names=["舒降之"], variety="葡萄柚", form="鲜榨果汁"
        )
        self.assertEqual(result.uncertainties, ())
        self.assertIn("G1", {item.guidance_id for item in result.items})

    def test_consult_compound_product_matches_components(self) -> None:
        result = self.center.consult(medication_names=["葆至能"], variety="西柚", form="果汁")
        self.assertIn("G1", {item.guidance_id for item in result.items})

    def test_unknown_product_surfaces_uncertainty_not_guess(self) -> None:
        result = self.center.consult(
            medication_names=["某进口胶囊"], variety="西柚", form="果汁"
        )
        self.assertTrue(result.uncertainties)
        self.assertIn("咨询", result.uncertainties[0])
        self.assertEqual(result.items, ())

    def test_sweet_orange_yields_nutrition_not_safety_advice(self) -> None:
        result = self.center.consult(medication_names=["舒降之"], variety="甜橙", form="果汁")
        by_id = {item.guidance_id: item for item in result.items}
        self.assertIn("G4", by_id)
        self.assertNotIn("G1", by_id)

    def test_flavor_drink_without_juice_has_no_interaction_advice(self) -> None:
        result = self.center.consult(
            medication_names=["舒降之"], variety="西柚味汽水", form="香精饮料"
        )
        self.assertEqual(result.items, ())
        self.assertEqual(result.uncertainties, ())

    def test_partial_citrus_info_asks_for_both_parts(self) -> None:
        result = self.center.consult(medication_names=["舒降之"], variety="西柚")
        self.assertTrue(any("加工形态" in message for message in result.uncertainties))

    def test_minimal_query_carries_no_identity_fields(self) -> None:
        self.assertEqual(
            set(MinimalMedicationQuery.__dataclass_fields__),
            {"ingredient_ids", "exposure_id", "exposure_component_ids"},
        )

    def test_patient_view_separates_safety_from_nutrition(self) -> None:
        result = self.center.consult(medication_names=["舒降之"], variety="西柚", form="果汁")
        view = patient_view(result.items, uncertainties=result.uncertainties)
        self.assertEqual(view["medication_safety"]["label"], "用药安全建议")
        self.assertEqual(view["general_nutrition"]["label"], "一般营养知识")
        self.assertEqual(
            [item["guidance_id"] for item in view["medication_safety"]["items"]], ["G1"]
        )
        self.assertEqual(view["general_nutrition"]["items"], [])

    def test_patient_view_surfaces_uncertainties(self) -> None:
        result = self.center.consult(medication_names=["某进口胶囊"], variety="西柚", form="果汁")
        view = patient_view(result.items, uncertainties=result.uncertainties)
        self.assertTrue(view["uncertainties"])

    def test_staff_view_traces_evidence_without_medical_record(self) -> None:
        result = self.center.consult(medication_names=["舒降之"], variety="西柚", form="果汁")
        view = staff_view(
            result.items, guidance=self.center.guidance, evidence=self.center.evidence
        )
        g1 = next(entry for entry in view if entry["guidance_id"] == "G1")
        self.assertEqual(g1["reviewed_by"], "李审核")
        self.assertEqual(g1["evidence"][0]["level"], "人体药动学研究")
        self.assertIn("老年患者（≥65岁）", g1["populations"])
        self.assertTrue(g1["evidence"][0]["literature"])
        blob = json.dumps(view, ensure_ascii=False)
        for word in ("病历", "身份证", "住址", "联系电话", "病案"):
            self.assertNotIn(word, blob)

    def test_trace_guidance_reaches_evidence_and_populations(self) -> None:
        trace = trace_guidance(
            "G1", guidance=self.center.guidance, evidence=self.center.evidence
        )
        self.assertIsNotNone(trace)
        self.assertEqual(trace.reviewed_by, "李审核")
        self.assertEqual(trace.evidence[0].evidence_id, "E1")
        self.assertEqual(trace.evidence[0].level, "人体药动学研究")
        self.assertTrue(trace.evidence[0].literature)
        self.assertIn("长期大量食用西柚制品者", trace.populations)


if __name__ == "__main__":
    unittest.main()
