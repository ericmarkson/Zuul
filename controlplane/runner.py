"""Phase A orchestrator: Tasks 1-7 of IMPLEMENTATION-PLAN.md Phase A, wired to the exact FRD
requirement text (quoted in each step below) rather than to a paraphrase of it."""

from __future__ import annotations

import fnmatch
import json
import shutil
import uuid
from pathlib import Path

from controlplane import gitops
from controlplane.checks import CheckResult, is_regression, run_check
from controlplane.escalate import EscalationCategory, EscalationReport, write_escalation_report
from controlplane.eventlog import DiagnosticLog, EventLog, EventType
from controlplane.gate import (
    ask_approval,
    present_gate,
    present_secret_findings,
    require_secret_acknowledgment,
)
from controlplane.plan import Plan, load_plan
from controlplane.secrets_scan import scan as scan_secrets


class Runner:
    def __init__(self, plan_path: Path, fixture_template: Path, edits_dir: Path, scratch_root: Path, auto_approve: bool = False):
        self.plan: Plan = load_plan(plan_path)
        self.fixture_template = fixture_template
        self.edits_dir = edits_dir
        self.auto_approve = auto_approve
        self.run_id = f"{self.plan.run_id_prefix}-{uuid.uuid4().hex[:8]}"
        self.run_dir = scratch_root / "runs" / self.run_id
        self.target_repo = self.run_dir / "target"
        self.event_log = EventLog(self.run_dir / "events.jsonl")
        self.diag_log = DiagnosticLog(self.run_dir / "diagnostics.log")

    # ---- setup -----------------------------------------------------------------

    def _materialize_target(self) -> None:
        shutil.copytree(
            self.fixture_template,
            self.target_repo,
            ignore=shutil.ignore_patterns("bin", "obj", ".git"),
        )
        gitops.git(self.target_repo, "init", "-q")
        gitops.git(self.target_repo, "config", "user.email", "installgraph@local")
        gitops.git(self.target_repo, "config", "user.name", "InstallGraph Control Plane")
        gitops.commit_all(self.target_repo, "baseline: pristine fixtures/sample-dotnet-app")
        self.diag_log.write(f"materialized target repo at {self.target_repo}")

    def _sync_installgraph_dir(self, message: str) -> str:
        """Copies the plan and the current event log into the target repo's .installgraph/
        directory and commits that snapshot. Used for the PLAN-1 plan commit and at each
        EXEC-6 sync point (PHASE_COMMITTED, and terminal states so the branch always holds a
        complete log for inspection)."""
        install_dir = self.target_repo / ".installgraph"
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.plan.source_path, install_dir / "plan.json")
        shutil.copyfile(self.event_log.path, install_dir / "events.jsonl")
        return gitops.commit_all(self.target_repo, message)

    # ---- check set ---------------------------------------------------------------

    def _run_check_set(self, phase_id: str) -> list[CheckResult]:
        results = []
        for check in self.plan.check_set:
            artifact = Path(check.result_artifact.format(run_dir=str(self.run_dir), phase_id=phase_id))
            command = [
                part.format(run_dir=str(self.run_dir), phase_id=phase_id, result_artifact=str(artifact))
                for part in check.command
            ]
            self.diag_log.write(f"phase={phase_id} check={check.id} command={command}")
            result = run_check(self.target_repo, check.id, command, artifact, check.result_format)
            self.diag_log.write(
                f"phase={phase_id} check={check.id} exit={result.exit_code} "
                f"not_run={result.not_run_reason} outcomes={result.test_outcomes}"
            )
            results.append(result)
            self.event_log.append(
                EventType.CHECK_RESULT,
                phase_id=phase_id,
                check_id=result.check_id,
                exit_code=result.exit_code,
                not_run_reason=result.not_run_reason,
                failed=sorted(result.failed_tests),
            )
        return results

    # ---- phase execution -----------------------------------------------------

    def _apply_edits(self, phase) -> None:
        for edit in phase.edits:
            src = self.edits_dir / edit.content_file
            dest = self.target_repo / edit.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    @staticmethod
    def _scope_violations(phase, changed: list[str]) -> list[str]:
        return [
            path
            for path in changed
            if not any(fnmatch.fnmatch(path, pattern) for pattern in phase.declared_scope)
        ]

    def _escalate(self, phase_id: str, category: EscalationCategory, summary: str, check_results: list[CheckResult], evidence: dict, compensating_action: str | None = None) -> None:
        self.event_log.append(EventType.ESCALATED, phase_id=phase_id, category=category.value, summary=summary)
        report = EscalationReport(
            run_id=self.run_id,
            phase_id=phase_id,
            category=category,
            summary=summary,
            check_results=[
                {"check_id": r.check_id, "exit_code": r.exit_code, "failed": sorted(r.failed_tests), "not_run_reason": r.not_run_reason}
                for r in check_results
            ],
            run_branch=f"run/{self.run_id}",
            baseline_commit=self.baseline_sha,
            diagnostic_log_path=str(self.diag_log.path),
            compensating_action=compensating_action,
            evidence=evidence,
        )
        report_path = self.run_dir / "escalation.json"
        write_escalation_report(report_path, report)
        self._sync_installgraph_dir(f"chore(installgraph): escalation on phase '{phase_id}'")
        self.diag_log.write(f"HALT: {summary}")
        print(f"\n[ESCALATION] {summary}")
        print(f"  category: {category.value}")
        print(f"  run branch: run/{self.run_id} (left intact, all phase commits preserved)")
        print(f"  baseline commit: {self.baseline_sha}")
        print(f"  report: {report_path}")
        print(f"  diagnostic log: {self.diag_log.path}")

    # ---- top level -----------------------------------------------------------

    def run(self) -> bool:
        self.diag_log.write(f"run_id={self.run_id} starting, plan={self.plan.source_path}")
        self.event_log.append(EventType.RUN_STARTED, run_id=self.run_id, plan_hash=self.plan.content_hash)

        # Task 2: baseline + refuse dirty tree + run branch
        self._materialize_target()
        self.baseline_sha = gitops.capture_baseline(self.target_repo)
        self.event_log.append(EventType.BASELINE_CAPTURED, sha=self.baseline_sha)

        # Task 3: baseline checks BEFORE the gate (QA-5)
        baseline_results = self._run_check_set("baseline")
        baseline_by_check = {r.check_id: r for r in baseline_results}

        # SECRET-1: scan the baseline, before the run branch even exists
        findings = scan_secrets(self.target_repo, self.baseline_sha)

        branch = gitops.create_run_branch(self.target_repo, self.run_id, self.baseline_sha)
        self.event_log.append(EventType.PLAN_GENERATED, source="operator-authored", path=str(self.plan.source_path))
        self._sync_installgraph_dir("plan: commit plan and event log (PLAN-1, control-plane artifacts only)")

        # Task 4: the gate. SECRET-1's acknowledgment gates entry to the gate itself;
        # declining either is treated identically to GATE_REJECTED (APPROVAL-5).
        present_secret_findings(findings)
        if not require_secret_acknowledgment(findings, auto_approve=self.auto_approve):
            return self._reject(branch, reason="secret_findings_not_acknowledged")

        present_gate(self.plan, self.baseline_sha, baseline_results)
        self.event_log.append(EventType.GATE_PRESENTED)
        if not ask_approval(auto_approve=self.auto_approve):
            return self._reject(branch, reason="operator_declined")

        self.event_log.append(EventType.GATE_APPROVED)
        print("\n[OK] Gate approved. Beginning unattended execution.\n")

        # Task 5 + 6: apply each phase, commit, scope-diff (fail closed), re-run checks as delta
        for phase in self.plan.phases:
            self.event_log.append(EventType.PHASE_STARTED, phase_id=phase.id)
            pre_sha = gitops.head(self.target_repo)

            self._apply_edits(phase)
            commit_sha = gitops.commit_all(self.target_repo, f"phase: {phase.id}")
            changed = gitops.changed_paths(self.target_repo, pre_sha, commit_sha)

            violations = self._scope_violations(phase, changed)
            if violations:
                self.event_log.append(EventType.SCOPE_VIOLATION_DETECTED, phase_id=phase.id, violations=violations, changed=changed)
                self._escalate(
                    phase.id,
                    EscalationCategory.SCOPE_CONFLICT,
                    f"phase '{phase.id}' modified path(s) outside its declared scope: {violations}",
                    check_results=[],
                    evidence={"declared_scope": phase.declared_scope, "changed": changed, "violations": violations},
                )
                return False

            phase_results = self._run_check_set(phase.id)
            regressions = [
                r for r in phase_results
                if r.check_id in baseline_by_check and is_regression(baseline_by_check[r.check_id], r)
            ]
            if regressions:
                self._escalate(
                    phase.id,
                    EscalationCategory.VALIDATION_LOOP,
                    f"phase '{phase.id}' introduced check failures not present at baseline",
                    check_results=phase_results,
                    evidence={
                        "regressed_checks": [r.check_id for r in regressions],
                        "new_failures": {r.check_id: sorted(r.failed_tests - baseline_by_check[r.check_id].failed_tests) for r in regressions},
                    },
                )
                return False

            self.event_log.append(EventType.PHASE_COMMITTED, phase_id=phase.id, commit=commit_sha)
            self._sync_installgraph_dir(f"chore(installgraph): sync event log after phase '{phase.id}'")
            print(f"[OK] Phase '{phase.id}' committed and verified ({commit_sha[:8]}).")

        self.event_log.append(EventType.RUN_COMPLETED, run_id=self.run_id)
        self._sync_installgraph_dir("chore(installgraph): run completed")
        self.diag_log.write("run completed successfully")
        print(f"\n[OK] Run {self.run_id} completed. Target repo: {self.target_repo}")
        return True

    def _reject(self, branch: str, reason: str) -> bool:
        """APPROVAL-5: rejection leaves the target codebase byte-identical, deletes the run
        branch (it holds only the plan commit at this point), exits non-zero."""
        self.event_log.append(EventType.GATE_REJECTED, reason=reason)
        gitops.checkout(self.target_repo, self.baseline_sha)
        gitops.delete_branch(self.target_repo, branch)
        self.diag_log.write(f"run rejected: {reason}; branch {branch} deleted; tree restored to baseline")
        print(f"\n[REJECTED] {reason}. Target codebase restored to baseline; run branch deleted.")
        return False
