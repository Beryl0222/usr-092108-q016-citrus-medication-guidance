import unittest

from src.models import ContentType
from src.publishing import Channel
from tests.support import VALID_FROM, VALID_UNTIL, approve_safety_guidance, build_service


class PublishingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = build_service()
        approve_safety_guidance(self.service)
        # 另一条不引用 ev-1 的提示，只发线上问答
        self.service.approve_guidance(
            "g-2",
            ContentType.NUTRITION_GENERAL,
            "柑橘类水果富含维生素 C，是一般营养知识。",
            ("ev-2",),
            reviewer="药师乙",
            valid_from=VALID_FROM,
            valid_until=VALID_UNTIL,
        )
        self.service.publish("g-1", [Channel.POSTER, Channel.PHARMACY_SCREEN])
        self.service.publish("g-2", [Channel.ONLINE_QA])

    def test_evidence_update_rolls_only_affected_channels(self) -> None:
        _, renewed = self.service.update_evidence(
            "ev-1",
            finding="更新后的人体研究结论",
            source="新文献",
            applicability="新适用边界",
            reviewer="药师甲",
            valid_until="2028-09-21",
        )
        self.assertEqual([g.guidance_id for g in renewed], ["g-1"])
        for channel in (Channel.POSTER, Channel.PHARMACY_SCREEN):
            current = self.service.channels.current(channel, "g-1")
            self.assertEqual(current.version, 2)
        # 线上问答未承载 g-1，不受影响；g-2 保持原版本
        self.assertIsNone(self.service.channels.current(Channel.ONLINE_QA, "g-1"))
        self.assertEqual(self.service.channels.current(Channel.ONLINE_QA, "g-2").version, 1)

    def test_patient_keeps_received_version_with_appended_correction(self) -> None:
        self.service.deliver("rc-1", "g-1")
        self.service.update_evidence(
            "ev-1",
            finding="更新后的人体研究结论",
            source="新文献",
            applicability="新适用边界",
            reviewer="药师甲",
            valid_until="2028-09-21",
            revised_texts={"g-1": "修订后的提示措辞，请咨询医生或药师。"},
        )
        count = self.service.correct("g-1", "更正：适用边界已更新，请以新版为准。")
        self.assertEqual(count, 1)
        receipt, corrections = self.service.channels.receipt_view("rc-1")
        # 患者保留当时收到的版本与正文，更正追加而不改写
        self.assertEqual(receipt.version, 1)
        self.assertIn("西柚汁", receipt.text)
        self.assertEqual(corrections, ("更正：适用边界已更新，请以新版为准。",))


if __name__ == "__main__":
    unittest.main()
