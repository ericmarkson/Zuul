"""Run state — FRD EXEC-6. The event log is the sole source of truth for run state; the fixed
event enum below is the complete list this document defines. DIAG-1's diagnostic log is a
separate, local-only, never-committed file — see DiagnosticLog."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class EventType(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    BASELINE_CAPTURED = "BASELINE_CAPTURED"
    PLAN_GENERATED = "PLAN_GENERATED"
    FINDING_DISCARDED = "FINDING_DISCARDED"
    GATE_PRESENTED = "GATE_PRESENTED"
    GATE_APPROVED = "GATE_APPROVED"
    GATE_REJECTED = "GATE_REJECTED"
    PHASE_STARTED = "PHASE_STARTED"
    CHECK_RESULT = "CHECK_RESULT"
    SCOPE_VIOLATION_DETECTED = "SCOPE_VIOLATION_DETECTED"
    PHASE_COMMITTED = "PHASE_COMMITTED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ESCALATED = "ESCALATED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_ABANDONED = "RUN_ABANDONED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    """Append-only JSONL log. Lives outside the target repo at all times (run_dir); the runner
    is responsible for syncing it into the target repo's .installgraph/ directory at the points
    EXEC-6 requires (the plan commit, and each PHASE_COMMITTED)."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: EventType, **fields) -> dict:
        record = {"ts": _now(), "event_type": event_type.value, **fields}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DiagnosticLog:
    """FRD DIAG-1: verbose, local-only, never committed, never exported. Escalation reports
    reference this file by path; they never inline its contents."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"[{_now()}] {message}\n")
