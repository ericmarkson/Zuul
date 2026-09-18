"""Escalation reporting — FRD ESCALATE-1/2. Fixed, closed taxonomy; no secrets or full source
content; always points at DIAG-1's diagnostic log by path rather than inlining it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class EscalationCategory(str, Enum):
    ENVIRONMENT = "environment"
    CREDENTIAL = "credential"
    TOOLING_GAP = "tooling-gap"
    VALIDATION_LOOP = "validation-loop"
    SCOPE_CONFLICT = "scope-conflict"
    BUDGET_EXCEEDED = "budget-exceeded"
    SIDE_EFFECT_UNCOMPENSATED = "side-effect-uncompensated"
    INTERNAL_ERROR = "internal-error"


@dataclass(frozen=True)
class EscalationReport:
    run_id: str
    phase_id: str
    category: EscalationCategory
    summary: str
    check_results: list[dict]
    run_branch: str
    baseline_commit: str
    diagnostic_log_path: str
    compensating_action: str | None
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "phase_id": self.phase_id,
            "category": self.category.value,
            "summary": self.summary,
            "check_results": self.check_results,
            "run_branch": self.run_branch,
            "baseline_commit": self.baseline_commit,
            "diagnostic_log_path": self.diagnostic_log_path,
            "compensating_action": self.compensating_action,
            "evidence": self.evidence,
        }


def write_escalation_report(path: Path, report: EscalationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
