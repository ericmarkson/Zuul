"""FRD EXEC-7's resume-report half. On startup, if a run's event log shows it is neither
RUN_COMPLETED, RUN_ABANDONED, nor ESCALATED, the system halts and reports rather than
automatically resuming or resetting -- resuming is an operator decision in v1."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from controlplane import gitops

TERMINAL_EVENT_TYPES = {"RUN_COMPLETED", "RUN_ABANDONED", "ESCALATED"}


@dataclass(frozen=True)
class ResumeReport:
    run_id: str
    last_committed_phase: dict | None
    last_event: dict
    total_events: int
    run_branch: str | None
    run_branch_head: str | None
    target_repo_dirty: bool | None
    target_repo_status: str | None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "last_committed_phase": self.last_committed_phase,
            "last_event": self.last_event,
            "total_events": self.total_events,
            "run_branch": self.run_branch,
            "run_branch_head": self.run_branch_head,
            "target_repo_dirty": self.target_repo_dirty,
            "target_repo_status": self.target_repo_status,
        }


def _read_events(event_log_path: Path) -> list[dict]:
    if not event_log_path.exists():
        return []
    return [json.loads(line) for line in event_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_incomplete(event_log_path: Path) -> bool:
    """True if the log has events but none of them is a terminal one."""
    events = _read_events(event_log_path)
    if not events:
        return False
    return not any(e["event_type"] in TERMINAL_EVENT_TYPES for e in events)


def build_resume_report(run_id: str, event_log_path: Path, target_repo: Path) -> ResumeReport:
    events = _read_events(event_log_path)
    last_committed_phase = None
    for e in events:
        if e["event_type"] == "PHASE_COMMITTED":
            last_committed_phase = e

    run_branch = f"run/{run_id}"
    run_branch_head = None
    target_repo_dirty = None
    target_repo_status = None

    if target_repo.exists() and (target_repo / ".git").exists():
        result = gitops.git(target_repo, "rev-parse", run_branch, check=False)
        if result.returncode == 0:
            run_branch_head = result.stdout.strip()
        status = gitops.git(target_repo, "status", "--porcelain")
        target_repo_status = status.stdout
        target_repo_dirty = bool(status.stdout.strip())

    return ResumeReport(
        run_id=run_id,
        last_committed_phase=last_committed_phase,
        last_event=events[-1] if events else {},
        total_events=len(events),
        run_branch=run_branch,
        run_branch_head=run_branch_head,
        target_repo_dirty=target_repo_dirty,
        target_repo_status=target_repo_status,
    )


def write_resume_report(path: Path, report: ResumeReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
