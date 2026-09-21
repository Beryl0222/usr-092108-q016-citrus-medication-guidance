"""渠道发布、按影响范围换版与患者更正留痕。

证据更新后，仅受影响的渠道换版；患者曾收到的内容保留当时版本快照，
更正以追加方式记录。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable

from .domain import Channel, GuidanceStatus
from .events import EventLog
from .guidance import GuidanceService


class PublishingError(ValueError):
    pass


@dataclass(frozen=True)
class GuidanceRef:
    guidance_id: str
    version: int


@dataclass(frozen=True)
class ChannelPublication:
    channel: Channel
    publication_version: int
    refs: tuple[GuidanceRef, ...]
    published_at: datetime
    reason: str = ""


@dataclass(frozen=True)
class Correction:
    correction_id: str
    reason: str
    corrected_text: str
    issued_at: datetime


@dataclass(frozen=True)
class ReceivedNotice:
    """患者曾收到的内容快照：原文保留，更正以追加方式记录。"""

    receipt_id: str
    guidance_id: str
    guidance_version: int
    text_snapshot: str
    received_at: datetime
    corrections: tuple[Correction, ...] = ()


@dataclass(frozen=True)
class ImpactReport:
    """一次换版的影响范围：受影响提示、已换版渠道、未受影响渠道。"""

    affected_guidance_ids: tuple[str, ...]
    reversioned: tuple[ChannelPublication, ...]
    untouched_channels: tuple[Channel, ...]


class Publisher:
    def __init__(self, guidance: GuidanceService, log: EventLog | None = None) -> None:
        self._guidance = guidance
        self._log = log
        self._publications: dict[Channel, list[ChannelPublication]] = {}
        self._receipts: dict[str, ReceivedNotice] = {}

    def publish(
        self,
        channel: Channel,
        refs: Iterable[GuidanceRef],
        *,
        at: datetime,
        reason: str = "",
    ) -> ChannelPublication:
        refs = tuple(refs)
        for ref in refs:
            version = self._guidance.get(ref.guidance_id, ref.version)
            if version is None:
                raise PublishingError(f"提示不存在：{ref.guidance_id} v{ref.version}")
            if version.status is not GuidanceStatus.APPROVED:
                raise PublishingError(f"只能发布已审校的提示：{ref.guidance_id} v{ref.version}")
        history = self._publications.setdefault(channel, [])
        publication = ChannelPublication(channel, len(history) + 1, refs, at, reason)
        history.append(publication)
        if self._log is not None:
            self._log.append(
                event_type="CHANNEL_UPDATED",
                aggregate_type="channel_publication",
                aggregate_id=channel.name,
                occurred_at=at,
                version=publication.publication_version,
                summary=reason or f"{channel.value}发布 v{publication.publication_version}",
            )
        return publication

    def current(self, channel: Channel) -> ChannelPublication | None:
        history = self._publications.get(channel)
        return history[-1] if history else None

    def reevaluate(
        self,
        affected_guidance_ids: Iterable[str],
        *,
        at: datetime,
        reason: str,
    ) -> ImpactReport:
        """按影响范围换版：仅当前发布内容涉及受影响提示的渠道换新版本。"""
        affected = tuple(sorted(set(affected_guidance_ids)))
        affected_set = set(affected)
        reversioned: list[ChannelPublication] = []
        untouched: list[Channel] = []
        for channel in sorted(self._publications, key=lambda c: c.name):
            current = self.current(channel)
            if current is None:
                continue
            new_refs: list[GuidanceRef] = []
            changed = False
            for ref in current.refs:
                if ref.guidance_id in affected_set:
                    changed = True
                    latest = self._guidance.latest(ref.guidance_id)
                    if latest is not None and latest.status is GuidanceStatus.APPROVED:
                        new_refs.append(GuidanceRef(latest.guidance_id, latest.version))
                    # 已撤回的提示从新版本中移除
                else:
                    new_refs.append(ref)
            new_refs_tuple = tuple(new_refs)
            if changed and new_refs_tuple != current.refs:
                reversioned.append(self.publish(channel, new_refs_tuple, at=at, reason=reason))
            else:
                untouched.append(channel)
        return ImpactReport(affected, tuple(reversioned), tuple(untouched))

    def deliver(self, receipt_id: str, guidance_id: str, *, at: datetime) -> ReceivedNotice:
        """记录患者收到的内容快照。"""
        if receipt_id in self._receipts:
            raise PublishingError(f"送达记录已存在：{receipt_id}")
        latest = self._guidance.latest(guidance_id)
        if latest is None or latest.status is not GuidanceStatus.APPROVED:
            raise PublishingError(f"提示不可送达：{guidance_id}")
        receipt = ReceivedNotice(receipt_id, latest.guidance_id, latest.version, latest.text, at)
        self._receipts[receipt_id] = receipt
        return receipt

    def correct(
        self,
        receipt_id: str,
        *,
        reason: str,
        corrected_text: str,
        at: datetime,
    ) -> ReceivedNotice:
        """对患者曾收到的内容追加更正，原快照保留。"""
        receipt = self._receipts.get(receipt_id)
        if receipt is None:
            raise PublishingError(f"送达记录不存在：{receipt_id}")
        correction = Correction(
            f"{receipt_id}-c{len(receipt.corrections) + 1}", reason, corrected_text, at
        )
        updated = replace(receipt, corrections=receipt.corrections + (correction,))
        self._receipts[receipt_id] = updated
        if self._log is not None:
            self._log.append(
                event_type="NOTICE_CORRECTED",
                aggregate_type="received_notice",
                aggregate_id=receipt_id,
                occurred_at=at,
                version=len(updated.corrections),
                summary=f"更正 {receipt_id}：{reason}",
            )
        return updated

    def receipt(self, receipt_id: str) -> ReceivedNotice | None:
        return self._receipts.get(receipt_id)

    def receipts_for(self, guidance_id: str) -> list[ReceivedNotice]:
        return [r for r in self._receipts.values() if r.guidance_id == guidance_id]
