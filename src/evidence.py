"""相互作用证据登记与更新：更新产生后继版本，旧版本保留并标记被替代。"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from .domain import EvidenceStatement, EvidenceStatus, EvidenceLevel, LiteratureRef
from .events import EventLog


class EvidenceError(ValueError):
    pass


class EvidenceRegistry:
    def __init__(self, log: EventLog | None = None) -> None:
        self._versions: dict[str, dict[int, EvidenceStatement]] = {}
        self._log = log

    def register(self, evidence: EvidenceStatement) -> EvidenceStatement:
        if evidence.evidence_id in self._versions:
            raise EvidenceError(f"证据编号已存在：{evidence.evidence_id}")
        if evidence.version != 1:
            raise EvidenceError("新证据 version 必须为 1")
        self._check_review(evidence)
        self._versions[evidence.evidence_id] = {1: evidence}
        self._emit(evidence, f"登记证据 {evidence.evidence_id}（{evidence.level.value}）")
        return evidence

    def update(
        self,
        evidence_id: str,
        *,
        reviewed_by: str,
        reviewed_at: datetime,
        valid_until: date,
        level: EvidenceLevel | None = None,
        effect: str | None = None,
        applicability: str | None = None,
        literature: tuple[LiteratureRef, ...] | None = None,
    ) -> EvidenceStatement:
        current = self.current(evidence_id)
        if current is None:
            raise EvidenceError(f"证据不存在：{evidence_id}")
        if current.status is EvidenceStatus.RETIRED:
            raise EvidenceError(f"已废止的证据不能更新：{evidence_id}")
        new_version = replace(
            current,
            version=current.version + 1,
            level=level or current.level,
            effect=effect or current.effect,
            applicability=applicability or current.applicability,
            literature=current.literature if literature is None else literature,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            valid_until=valid_until,
            status=EvidenceStatus.ACTIVE,
        )
        self._check_review(new_version)
        slot = self._versions[evidence_id]
        slot[current.version] = replace(current, status=EvidenceStatus.SUPERSEDED)
        slot[new_version.version] = new_version
        self._emit(new_version, f"更新证据 {evidence_id} 至 v{new_version.version}")
        return new_version

    def retire(self, evidence_id: str, *, at: datetime, reason: str) -> EvidenceStatement:
        current = self.current(evidence_id)
        if current is None:
            raise EvidenceError(f"证据不存在：{evidence_id}")
        slot = self._versions[evidence_id]
        slot[current.version] = replace(current, status=EvidenceStatus.SUPERSEDED)
        retired = replace(current, version=current.version + 1, status=EvidenceStatus.RETIRED)
        slot[retired.version] = retired
        self._emit(retired, f"废止证据 {evidence_id}：{reason}", occurred_at=at)
        return retired

    def current(self, evidence_id: str) -> EvidenceStatement | None:
        slot = self._versions.get(evidence_id)
        return slot[max(slot)] if slot else None

    def get(self, evidence_id: str, version: int) -> EvidenceStatement | None:
        return self._versions.get(evidence_id, {}).get(version)

    def history(self, evidence_id: str) -> tuple[EvidenceStatement, ...]:
        slot = self._versions.get(evidence_id, {})
        return tuple(slot[v] for v in sorted(slot))

    def _check_review(self, evidence: EvidenceStatement) -> None:
        if not evidence.reviewed_by:
            raise EvidenceError("证据必须登记审校人")
        if evidence.reviewed_at is None:
            raise EvidenceError("证据必须登记审校时间")
        if evidence.valid_until is None:
            raise EvidenceError("证据必须登记有效期")

    def _emit(
        self, evidence: EvidenceStatement, summary: str, occurred_at: datetime | None = None
    ) -> None:
        if self._log is None:
            return
        self._log.append(
            event_type="EVIDENCE_REVIEWED",
            aggregate_type="evidence_statement",
            aggregate_id=evidence.evidence_id,
            occurred_at=occurred_at or evidence.reviewed_at,
            version=evidence.version,
            summary=summary,
        )
