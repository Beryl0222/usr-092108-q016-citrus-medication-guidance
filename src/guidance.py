"""建议措辞的审校与版本管理，内置安全措辞护栏。

措辞规范（与 README 一致）：
- 不得出现指令性停药、换药、调整剂量或推断诊断的措辞；
- 证据仅来自动物或体外研究时，必须标注不确定性并引导咨询；
- 食品建议统一使用「避免食用/饮用」，不使用「停用」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime

from .domain import (
    HUMAN_LEVELS,
    Audience,
    EvidenceLevel,
    EvidenceStatus,
    GuidanceKind,
    GuidanceStatus,
    GuidanceVersion,
    RiskPopulation,
)
from .evidence import EvidenceRegistry
from .events import EventLog

_DIRECTIVE_RE = re.compile(
    r"(请|可|可以|建议|应当?|需|需要|立即|马上)"
    r"(自行)?"
    r"(停药|停用|停止服用|停止服药|换药|改用|换成|调整剂量|加量|减量)"
)
_DIAGNOSIS_RE = re.compile(r"(诊断为|确诊为|您患有|你患有)")
_UNCERTAINTY_MARKERS = ("证据有限", "尚不确定", "不确定", "尚需", "缺乏人体", "人体研究不足", "临床意义尚不明确")
_CONSULT_MARKER = "咨询"


@dataclass(frozen=True)
class LintIssue:
    rule: str
    detail: str


class GuidanceRejected(ValueError):
    def __init__(self, issues: list[LintIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("；".join(f"{issue.rule}：{issue.detail}" for issue in issues))


def lint_text(text: str, *, levels: tuple[EvidenceLevel, ...] = ()) -> list[LintIssue]:
    """安全措辞护栏：返回全部违规项，空列表表示通过。"""
    issues: list[LintIssue] = []
    directive = _DIRECTIVE_RE.search(text)
    if directive:
        issues.append(
            LintIssue("禁止指令性停药换药", f"命中措辞「{directive.group(0)}」，请改为风险提示并引导咨询")
        )
    diagnosis = _DIAGNOSIS_RE.search(text)
    if diagnosis:
        issues.append(LintIssue("禁止推断诊断", f"命中措辞「{diagnosis.group(0)}」"))
    if levels and not any(level in HUMAN_LEVELS for level in levels):
        if not any(marker in text for marker in _UNCERTAINTY_MARKERS):
            issues.append(
                LintIssue("低等级证据须标注不确定性", "证据仅来自动物或体外研究，措辞须说明证据有限")
            )
        if _CONSULT_MARKER not in text:
            issues.append(LintIssue("低等级证据须引导咨询", "措辞须引导患者咨询医生或药师"))
    return issues


class GuidanceService:
    """提示的审校、修订与撤回。审校通过方可发布。"""

    def __init__(self, evidence: EvidenceRegistry, log: EventLog | None = None) -> None:
        self._evidence = evidence
        self._log = log
        self._versions: dict[str, dict[int, GuidanceVersion]] = {}
        self._populations: dict[str, RiskPopulation] = {}

    def register_population(self, population: RiskPopulation) -> None:
        self._populations[population.population_id] = population

    def population(self, population_id: str) -> RiskPopulation | None:
        return self._populations.get(population_id)

    def approve(
        self,
        *,
        guidance_id: str,
        kind: GuidanceKind,
        audience: Audience,
        text: str,
        evidence_ids: tuple[str, ...] = (),
        population_ids: tuple[str, ...] = (),
        exposure_ids: tuple[str, ...] = (),
        reviewed_by: str,
        approved_at: datetime,
        valid_until: date,
    ) -> GuidanceVersion:
        if guidance_id in self._versions:
            raise GuidanceRejected([LintIssue("编号冲突", f"{guidance_id} 已存在，请使用 revise")])
        version = GuidanceVersion(
            guidance_id=guidance_id,
            version=1,
            kind=kind,
            audience=audience,
            text=text,
            evidence_ids=tuple(evidence_ids),
            population_ids=tuple(population_ids),
            exposure_ids=tuple(exposure_ids),
            reviewed_by=reviewed_by,
            approved_at=approved_at,
            valid_until=valid_until,
        )
        self._validate(version)
        self._versions[guidance_id] = {1: version}
        self._emit(version, "GUIDANCE_APPROVED", f"审校通过提示 {guidance_id} v1")
        return version

    def revise(
        self,
        guidance_id: str,
        *,
        text: str | None = None,
        evidence_ids: tuple[str, ...] | None = None,
        population_ids: tuple[str, ...] | None = None,
        exposure_ids: tuple[str, ...] | None = None,
        reviewed_by: str,
        approved_at: datetime,
        valid_until: date,
    ) -> GuidanceVersion:
        current = self.latest(guidance_id)
        if current is None:
            raise GuidanceRejected([LintIssue("编号不存在", guidance_id)])
        if current.status is GuidanceStatus.WITHDRAWN:
            raise GuidanceRejected([LintIssue("已撤回", "已撤回的提示不能修订")])
        new_version = replace(
            current,
            version=current.version + 1,
            text=current.text if text is None else text,
            evidence_ids=current.evidence_ids if evidence_ids is None else tuple(evidence_ids),
            population_ids=current.population_ids if population_ids is None else tuple(population_ids),
            exposure_ids=current.exposure_ids if exposure_ids is None else tuple(exposure_ids),
            reviewed_by=reviewed_by,
            approved_at=approved_at,
            valid_until=valid_until,
            status=GuidanceStatus.APPROVED,
        )
        self._validate(new_version)
        slot = self._versions[guidance_id]
        slot[current.version] = replace(current, status=GuidanceStatus.SUPERSEDED)
        slot[new_version.version] = new_version
        self._emit(new_version, "GUIDANCE_APPROVED", f"修订提示 {guidance_id} 至 v{new_version.version}")
        return new_version

    def withdraw(self, guidance_id: str, *, at: datetime, reason: str) -> GuidanceVersion:
        current = self.latest(guidance_id)
        if current is None:
            raise GuidanceRejected([LintIssue("编号不存在", guidance_id)])
        if current.status is GuidanceStatus.WITHDRAWN:
            raise GuidanceRejected([LintIssue("已撤回", guidance_id)])
        slot = self._versions[guidance_id]
        slot[current.version] = replace(current, status=GuidanceStatus.SUPERSEDED)
        withdrawn = replace(current, version=current.version + 1, status=GuidanceStatus.WITHDRAWN)
        slot[withdrawn.version] = withdrawn
        self._emit(withdrawn, "GUIDANCE_WITHDRAWN", f"撤回提示 {guidance_id}：{reason}", occurred_at=at)
        return withdrawn

    def latest(self, guidance_id: str) -> GuidanceVersion | None:
        slot = self._versions.get(guidance_id)
        return slot[max(slot)] if slot else None

    def get(self, guidance_id: str, version: int) -> GuidanceVersion | None:
        return self._versions.get(guidance_id, {}).get(version)

    def approved(self) -> list[GuidanceVersion]:
        return [
            version
            for version in (self.latest(guidance_id) for guidance_id in sorted(self._versions))
            if version is not None and version.status is GuidanceStatus.APPROVED
        ]

    def find_by_evidence(self, evidence_id: str) -> list[GuidanceVersion]:
        return [g for g in self.approved() if evidence_id in g.evidence_ids]

    def _validate(self, version: GuidanceVersion) -> None:
        issues: list[LintIssue] = []
        if not version.text.strip():
            issues.append(LintIssue("措辞为空", "建议措辞不能为空"))
        if not version.reviewed_by.strip():
            issues.append(LintIssue("缺少审校人", "必须登记审校人"))
        if version.approved_at is None:
            issues.append(LintIssue("缺少审校时间", "必须登记审校时间"))
        if version.valid_until is None:
            issues.append(LintIssue("缺少有效期", "必须登记有效期"))
        elif version.approved_at is not None and version.valid_until <= version.approved_at.date():
            issues.append(LintIssue("有效期无效", "有效期必须晚于审校日期"))
        levels: tuple[EvidenceLevel, ...] = ()
        if version.kind is GuidanceKind.MEDICATION_SAFETY:
            if not version.evidence_ids:
                issues.append(LintIssue("缺少证据", "用药安全建议必须关联至少一条证据"))
            if not version.population_ids:
                issues.append(LintIssue("缺少适用人群", "用药安全建议必须登记适用人群"))
            collected: list[EvidenceLevel] = []
            for evidence_id in version.evidence_ids:
                evidence = self._evidence.current(evidence_id)
                if evidence is None:
                    issues.append(LintIssue("证据不存在", evidence_id))
                elif evidence.status is not EvidenceStatus.ACTIVE:
                    issues.append(LintIssue("证据非现行", f"{evidence_id} 已被替代或废止"))
                else:
                    collected.append(evidence.level)
            levels = tuple(collected)
        for population_id in version.population_ids:
            if population_id not in self._populations:
                issues.append(LintIssue("人群未登记", population_id))
        if version.text.strip():
            issues.extend(lint_text(version.text, levels=levels))
        if issues:
            raise GuidanceRejected(issues)

    def _emit(
        self,
        version: GuidanceVersion,
        event_type: str,
        summary: str,
        occurred_at: datetime | None = None,
    ) -> None:
        if self._log is None:
            return
        self._log.append(
            event_type=event_type,
            aggregate_type="guidance_version",
            aggregate_id=version.guidance_id,
            occurred_at=occurred_at or version.approved_at,
            version=version.version,
            summary=summary,
        )
