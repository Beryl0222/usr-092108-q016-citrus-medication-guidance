"""渠道发布与更正。

证据更新后，旧海报、药房屏幕和线上问答按影响范围换版——只有实际
承载受影响提示的渠道才换版；患者曾收到的内容保留当时版本，更正以
追加方式记录，原文不改写。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import GuidanceVersion


class Channel(str, Enum):
    POSTER = "poster"                    # 海报
    PHARMACY_SCREEN = "pharmacy_screen"  # 药房屏幕
    ONLINE_QA = "online_qa"              # 线上问答


@dataclass(frozen=True)
class ChannelPublication:
    """某渠道当前承载的提示版本。"""

    channel: Channel
    guidance_id: str
    version: int
    published_at: str


@dataclass(frozen=True)
class PatientReceipt:
    """患者曾收到的内容快照：版本与正文在送达时冻结。"""

    receipt_id: str
    guidance_id: str
    version: int
    text: str
    content_type: str
    received_at: str


class ChannelRegistry:
    """记录各渠道当前版本、患者送达快照与追加的更正。"""

    def __init__(self) -> None:
        self._current: dict[Channel, dict[str, ChannelPublication]] = {
            channel: {} for channel in Channel
        }
        self._receipts: dict[str, PatientReceipt] = {}
        self._corrections: dict[str, list[str]] = {}

    def publish(
        self, guidance: GuidanceVersion, channels: list[Channel], published_at: str
    ) -> list[ChannelPublication]:
        publications = []
        for channel in channels:
            publication = ChannelPublication(
                channel, guidance.guidance_id, guidance.version, published_at
            )
            self._current[channel][guidance.guidance_id] = publication
            publications.append(publication)
        return publications

    def rollover(self, guidance: GuidanceVersion, published_at: str) -> list[ChannelPublication]:
        """按影响范围换版：只更新当前承载该提示的渠道。"""
        return self.publish(guidance, self.channels_carrying(guidance.guidance_id), published_at)

    def current(self, channel: Channel, guidance_id: str) -> ChannelPublication | None:
        return self._current[channel].get(guidance_id)

    def channels_carrying(self, guidance_id: str) -> list[Channel]:
        return [
            channel
            for channel, entries in self._current.items()
            if guidance_id in entries
        ]

    def deliver(
        self, receipt_id: str, guidance: GuidanceVersion, received_at: str
    ) -> PatientReceipt:
        """把当前版本送达患者，快照自此冻结。"""
        receipt = PatientReceipt(
            receipt_id=receipt_id,
            guidance_id=guidance.guidance_id,
            version=guidance.version,
            text=guidance.text,
            content_type=guidance.content_type.value,
            received_at=received_at,
        )
        self._receipts[receipt_id] = receipt
        return receipt

    def append_correction(self, receipt_id: str, correction: str) -> None:
        """为患者已收到的内容追加更正；原文与版本保持不变。"""
        if receipt_id not in self._receipts:
            raise KeyError(f"未知的送达记录：{receipt_id}")
        self._corrections.setdefault(receipt_id, []).append(correction)

    def receipts_for(self, guidance_id: str) -> tuple[PatientReceipt, ...]:
        return tuple(
            r for r in self._receipts.values() if r.guidance_id == guidance_id
        )

    def receipt_view(self, receipt_id: str) -> tuple[PatientReceipt, tuple[str, ...]]:
        """患者视角：当时的版本快照 + 按时间追加的更正。"""
        receipt = self._receipts[receipt_id]
        return receipt, tuple(self._corrections.get(receipt_id, ()))
