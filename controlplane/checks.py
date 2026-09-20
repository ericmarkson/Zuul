"""Check execution and verdict derivation — FRD QA-1 (multi-check reporting, not-run is not a
pass), QA-2 (verdict from exit code + machine-readable artifact only, never from stdout text or a
model's summary), QA-5 (delta-vs-baseline)."""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

TRX_NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    exit_code: int | None
    test_outcomes: dict[str, str] = field(default_factory=dict)  # test name -> Passed/Failed
    not_run_reason: str | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def failed_tests(self) -> set[str]:
        return {name for name, outcome in self.test_outcomes.items() if outcome != "Passed"}

    @property
    def not_run(self) -> bool:
        return self.not_run_reason is not None

    # stdout/stderr are captured for commentary only (e.g. LLM retry feedback, DIAG-1) --
    # nothing in this module or is_regression() below ever reads them for pass/fail. QA-2.


def run_check(cwd: Path, check_id: str, command: list[str], result_artifact: Path, result_format: str) -> CheckResult:
    """Runs `command`; the verdict is derived ONLY from the process exit code and, when present,
    the machine-readable result_artifact. Stdout/stderr are never inspected for pass/fail —
    they go to the diagnostic log (DIAG-1) as commentary only. QA-2."""
    result_artifact.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=300)
    except FileNotFoundError as exc:
        return CheckResult(check_id=check_id, exit_code=None, not_run_reason=f"toolchain unavailable: {exc}")
    except subprocess.TimeoutExpired:
        return CheckResult(check_id=check_id, exit_code=None, not_run_reason="check timed out")

    outcomes = _parse_result_artifact(result_artifact, result_format) if result_artifact.exists() else {}

    # QA-2: the exit code governs even when the artifact disagrees with it (or there is no
    # artifact at all) — a check must not be able to talk its way to a pass by claiming success
    # in its own output while the process that ran it exited non-zero.
    if proc.returncode != 0 and not any(outcome != "Passed" for outcome in outcomes.values()):
        outcomes = {**outcomes, "__process_exit__": "Failed"}

    return CheckResult(
        check_id=check_id, exit_code=proc.returncode, test_outcomes=outcomes,
        stdout=proc.stdout, stderr=proc.stderr,
    )


def _parse_result_artifact(path: Path, result_format: str) -> dict[str, str]:
    if result_format == "junit":
        return _parse_junit(path)
    if result_format == "trx":
        return _parse_trx(path)
    raise ValueError(f"unsupported result_format: {result_format}")


def _parse_junit(path: Path) -> dict[str, str]:
    tree = ET.parse(path)
    root = tree.getroot()
    outcomes: dict[str, str] = {}
    for testcase in root.findall(".//testcase"):
        name = testcase.get("name")
        if name is None:
            continue
        has_failure = testcase.find("failure") is not None
        has_error = testcase.find("error") is not None
        outcomes[name] = "Failed" if (has_failure or has_error) else "Passed"
    return outcomes


def _parse_trx(path: Path) -> dict[str, str]:
    tree = ET.parse(path)
    root = tree.getroot()
    outcomes: dict[str, str] = {}
    for result in root.findall(".//t:UnitTestResult", TRX_NS):
        name = result.get("testName")
        if name is not None:
            outcomes[name] = result.get("outcome", "Unknown")
    return outcomes


def is_regression(baseline: CheckResult, current: CheckResult) -> bool:
    """QA-5: a check already failing at baseline and still failing identically is not a fault.
    A check newly failing, or a check that flips from executable to not-run, is a regression."""
    if current.not_run and not baseline.not_run:
        return True
    new_failures = current.failed_tests - baseline.failed_tests
    return bool(new_failures)
