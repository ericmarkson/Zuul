"""Phase A orchestrator: Tasks 1-7 of IMPLEMENTATION-PLAN.md Phase A, wired to the exact FRD
requirement text (quoted in each step below) rather than to a paraphrase of it."""

from __future__ import annotations

import fnmatch
import json
import shutil
import uuid
from pathlib import Path

from controlplane import gitops
from controlplane.checks import CheckResult, is_failure, is_regression, run_check
from controlplane.escalate import EscalationCategory, EscalationReport, write_escalation_report
from controlplane.eventlog import DiagnosticLog, EventLog, EventType
from controlplane.gate import (
    ask_approval,
    present_gate,
    present_secret_findings,
    require_secret_acknowledgment,
)
from controlplane.llm_implementer import MalformedResponse, request_edits
from controlplane.model_provider import BudgetedProvider, BudgetExceeded
from controlplane.plan import Plan, load_plan
from controlplane.resume import build_resume_report, is_incomplete, write_resume_report
from controlplane.run_lock import RunLock, RunLockHeld
from controlplane.secrets_scan import scan as scan_secrets


class Runner:
    def __init__(
        self,
        plan_path: Path,
        fixture_template: Path,
        edits_dir: Path,
        scratch_root: Path,
        auto_approve: bool = False,
        model_provider: BudgetedProvider | None = None,
        retry_budget: int = 2,
        llm_max_output_tokens: int = 8000,
        llm_max_tool_rounds: int = 6,
        run_id: str | None = None,
    ):
        self.plan: Plan = load_plan(plan_path)
        self.fixture_template = fixture_template
        self.edits_dir = edits_dir
        self.auto_approve = auto_approve
        self.model_provider = model_provider
        self.retry_budget = retry_budget
        self.llm_max_output_tokens = llm_max_output_tokens
        self.llm_max_tool_rounds = llm_max_tool_rounds
        # EXEC-7: a caller-supplied run_id is what makes a run addressable across process
        # restarts. Without one, every invocation is a fresh run by construction and the
        # resume path below is simply never triggered -- which is correct, not a gap: nothing
        # to resume into unless the operator names the same run twice.
        self.run_id = run_id or f"{self.plan.run_id_prefix}-{uuid.uuid4().hex[:8]}"
        self.run_dir = scratch_root / "runs" / self.run_id
        self.target_repo = self.run_dir / "target"
        self.verifier_repo = self.run_dir / "verifier"
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

    def _run_check_set(self, phase_id: str, checks: list | None = None) -> list[CheckResult]:
        """EXEC-10: checks never run in the implementer's own working directory. Before each
        check set, the verifier's independent worktree is moved (detached) to whatever commit
        the implementer last produced, and every check command executes there instead.

        PLAN-5: a phase may declare its own check set (e.g. a generated phase whose node
        template knows a specific file should now exist); `checks=None` means "use the plan's
        default `check_set`," which is what baseline and hand-authored phases always do."""
        checks = checks if checks is not None else self.plan.check_set
        verify_commit = gitops.head(self.target_repo)
        gitops.checkout(self.verifier_repo, verify_commit)
        self.diag_log.write(f"phase={phase_id} verifier worktree checked out at {verify_commit}")

        results = []
        for check in checks:
            artifact = Path(check.result_artifact.format(run_dir=str(self.run_dir), phase_id=phase_id))
            command = [
                part.format(run_dir=str(self.run_dir), phase_id=phase_id, result_artifact=str(artifact))
                for part in check.command
            ]
            self.diag_log.write(f"phase={phase_id} check={check.id} command={command}")
            result = run_check(self.verifier_repo, check.id, command, artifact, check.result_format)
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

    def _apply_llm_edits(self, phase, prior_failure_feedback: str | None) -> tuple[int, int]:
        """Phase E: no pre-authored edits exist for this phase (the audit-derived path), so the
        model proposes them. Whatever it returns is written and committed as-is -- EXEC-2:
        detection (INTEGRITY-3's post-commit scope diff) is the enforcement mechanism, not
        pre-filtering what the model is allowed to propose."""
        check_commands = [c.command for c in self.plan.check_set]
        result = request_edits(
            self.model_provider,
            phase.description,
            phase.declared_scope,
            self.target_repo,
            check_commands,
            max_output_tokens=self.llm_max_output_tokens,
            prior_failure_feedback=prior_failure_feedback,
            max_tool_rounds=self.llm_max_tool_rounds,
        )
        for edit in result.edits:
            dest = self.target_repo / edit.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(edit.content, encoding="utf-8")
        self.diag_log.write(f"phase={phase.id} LLM proposed edits to: {[e.path for e in result.edits]}")
        return result.input_tokens, result.output_tokens

    @staticmethod
    def _scope_violations(phase, changed: list[str]) -> list[str]:
        return [
            path
            for path in changed
            if not any(fnmatch.fnmatch(path, pattern) for pattern in phase.declared_scope)
        ]

    @staticmethod
    def _build_failure_feedback(phase_results: list[CheckResult], baseline_by_check: dict) -> str:
        lines = []
        for r in phase_results:
            baseline = baseline_by_check.get(r.check_id)
            new_failures = sorted(r.failed_tests - baseline.failed_tests) if baseline else sorted(r.failed_tests)
            lines.append(f"check '{r.check_id}': exit_code={r.exit_code}, new_failures={new_failures}")
            excerpt = (r.stdout[-1500:] + "\n" + r.stderr[-1500:]).strip()
            if excerpt:
                lines.append(f"output excerpt:\n{excerpt}")
        return "\n".join(lines)

    def _execute_phase(self, phase, baseline_by_check: dict) -> bool:
        """EXEC-3: bounded retry budget per phase. A retry re-runs the implementer step (LLM
        path only -- a scripted phase is deterministic, so a retry would reproduce the same
        result and is skipped) after an INTEGRITY-8 file-only baseline reset back to the
        phase's own pre-attempt commit. Scope violations are never retried -- they escalate
        immediately, fail closed, exactly as in Phase A/D. Budget overruns are never retried
        either -- BUDGET-2 requires an immediate halt."""
        self.event_log.append(EventType.PHASE_STARTED, phase_id=phase.id)
        pre_sha = gitops.head(self.target_repo)
        cumulative_input_tokens = 0
        cumulative_output_tokens = 0

        if self.model_provider and not phase.edits:
            self.model_provider.start_phase()

        prior_failure_feedback = None
        attempt = 0
        while True:
            attempt += 1
            if attempt > 1:
                gitops.git(self.target_repo, "reset", "--hard", pre_sha)
                self.diag_log.write(f"phase={phase.id} attempt={attempt}: reset to pre-attempt baseline {pre_sha}")

            if phase.edits:
                self._apply_edits(phase)
            else:
                try:
                    in_toks, out_toks = self._apply_llm_edits(phase, prior_failure_feedback)
                    cumulative_input_tokens += in_toks
                    cumulative_output_tokens += out_toks
                except BudgetExceeded as e:
                    self.event_log.append(EventType.BUDGET_EXCEEDED, phase_id=phase.id, kind=e.kind, limit=e.limit, actual=e.actual)
                    self._escalate(
                        phase.id, EscalationCategory.BUDGET_EXCEEDED,
                        f"phase '{phase.id}' exceeded its {e.kind} budget: {e.actual} > {e.limit}",
                        check_results=[], evidence={"kind": e.kind, "limit": e.limit, "actual": e.actual},
                    )
                    return False
                except MalformedResponse as e:
                    if attempt > self.retry_budget:
                        self._escalate(
                            phase.id, EscalationCategory.VALIDATION_LOOP,
                            f"phase '{phase.id}' implementer produced unusable output after {attempt} attempt(s): {e}",
                            check_results=[], evidence={"attempts": attempt, "last_error": str(e)},
                        )
                        return False
                    prior_failure_feedback = f"Your previous response could not be used: {e}"
                    self.diag_log.write(f"phase={phase.id} attempt={attempt}: malformed LLM response, retrying: {e}")
                    continue

            commit_sha = gitops.commit_all(self.target_repo, f"phase: {phase.id}" + (f" (attempt {attempt})" if attempt > 1 else ""))
            changed = gitops.changed_paths(self.target_repo, pre_sha, commit_sha)

            violations = self._scope_violations(phase, changed)
            if violations:
                self.event_log.append(EventType.SCOPE_VIOLATION_DETECTED, phase_id=phase.id, violations=violations, changed=changed)
                self._escalate(
                    phase.id, EscalationCategory.SCOPE_CONFLICT,
                    f"phase '{phase.id}' modified path(s) outside its declared scope: {violations}",
                    check_results=[],
                    evidence={"declared_scope": phase.declared_scope, "changed": changed, "violations": violations, "attempt": attempt},
                )
                return False

            phase_results = self._run_check_set(phase.id, phase.checks)
            # PLAN-5: a phase may run checks the baseline never did (a generated phase's own
            # node-template-declared check). Those have no baseline entry to compare against --
            # there is no "pre-existing failure" tolerance for a check that is new to this
            # phase, so any failure there counts directly, not as a delta.
            regressions = [
                r for r in phase_results
                if (r.check_id in baseline_by_check and is_regression(baseline_by_check[r.check_id], r))
                or (r.check_id not in baseline_by_check and is_failure(r))
            ]
            if regressions:
                if attempt > self.retry_budget:
                    self._escalate(
                        phase.id, EscalationCategory.VALIDATION_LOOP,
                        f"phase '{phase.id}' introduced check failures not present at baseline, after {attempt} attempt(s)",
                        check_results=phase_results,
                        evidence={
                            "regressed_checks": [r.check_id for r in regressions],
                            "new_failures": {
                                r.check_id: sorted(r.failed_tests - (baseline_by_check[r.check_id].failed_tests if r.check_id in baseline_by_check else set()))
                                for r in regressions
                            },
                            "attempts": attempt,
                        },
                    )
                    return False
                prior_failure_feedback = self._build_failure_feedback(phase_results, baseline_by_check)
                self.diag_log.write(f"phase={phase.id} attempt={attempt}: check regression, retrying")
                continue

            self.event_log.append(
                EventType.PHASE_COMMITTED, phase_id=phase.id, commit=commit_sha, attempts=attempt,
                input_tokens=cumulative_input_tokens, output_tokens=cumulative_output_tokens,
                run_tokens_total=self.model_provider.run_tokens_used if self.model_provider else 0,
            )
            self._sync_installgraph_dir(f"chore(installgraph): sync event log after phase '{phase.id}'")
            print(f"[OK] Phase '{phase.id}' committed and verified ({commit_sha[:8]}, {attempt} attempt(s)).")
            return True

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
        # EXEC-7: exclusive lock keyed to run id, refuse a second process against the same run.
        lock = RunLock(self.run_dir / "run.lock")
        try:
            lock.acquire()
        except RunLockHeld as exc:
            print(f"\n[REFUSED] {exc}")
            return False

        try:
            return self._run_locked()
        finally:
            lock.release()

    def _run_locked(self) -> bool:
        # EXEC-7: on startup, a non-terminal prior event log halts with a resume report rather
        # than auto-resuming or auto-resetting. This only ever triggers when the caller reuses
        # a run_id explicitly -- a fresh UUID-based run_id (the default) never collides with
        # anything, by construction.
        if is_incomplete(self.event_log.path):
            report = build_resume_report(self.run_id, self.event_log.path, self.target_repo)
            report_path = self.run_dir / "resume_report.json"
            write_resume_report(report_path, report)
            self.diag_log.write(f"HALT: run_id={self.run_id} has incomplete prior state; refusing to auto-resume or reset")
            print(f"\n[HALT] Run '{self.run_id}' has incomplete prior state and will not be auto-resumed or reset.")
            print(f"  last event: {report.last_event.get('event_type', '(none)')}")
            last_phase = report.last_committed_phase.get("phase_id") if report.last_committed_phase else "(none)"
            print(f"  last committed phase: {last_phase}")
            print(f"  run branch head: {report.run_branch_head}")
            print(f"  target repo working tree dirty: {report.target_repo_dirty}")
            print(f"  resume report: {report_path}")
            print("  Resuming is an operator decision in v1 — inspect the report and the run branch, then decide.")
            return False

        if self.target_repo.exists():
            print(f"\n[REFUSED] run_id '{self.run_id}' already has a completed run at {self.target_repo}. Choose a new run id.")
            return False

        self.diag_log.write(f"run_id={self.run_id} starting, plan={self.plan.source_path}")
        self.event_log.append(EventType.RUN_STARTED, run_id=self.run_id, plan_hash=self.plan.content_hash)

        # Task 2: baseline + refuse dirty tree
        self._materialize_target()
        self.baseline_sha = gitops.capture_baseline(self.target_repo)
        self.event_log.append(EventType.BASELINE_CAPTURED, sha=self.baseline_sha)

        # EXEC-10: the verifier's independent worktree, set up once baseline exists. Detached,
        # so it never collides with whatever branch the implementer's own working directory has
        # checked out.
        gitops.add_worktree(self.target_repo, self.verifier_repo, self.baseline_sha)
        self.diag_log.write(f"verifier worktree created at {self.verifier_repo}")

        try:
            return self._run_after_worktree_setup()
        finally:
            gitops.remove_worktree(self.target_repo, self.verifier_repo)

    def _run_after_worktree_setup(self) -> bool:
        # Task 3: baseline checks BEFORE the gate (QA-5), executed in the verifier's worktree
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

        model_name = getattr(getattr(self.model_provider, "inner", None), "model", None) if self.model_provider else None
        present_gate(self.plan, self.baseline_sha, baseline_results, model_in_use=self.model_provider is not None, model_name=model_name)
        self.event_log.append(EventType.GATE_PRESENTED)
        if not ask_approval(auto_approve=self.auto_approve):
            return self._reject(branch, reason="operator_declined")

        self.event_log.append(EventType.GATE_APPROVED)
        print("\n[OK] Gate approved. Beginning unattended execution.\n")

        # Task 5 + 6: apply each phase, commit, scope-diff (fail closed), re-run checks as delta
        for phase in self.plan.phases:
            if not self._execute_phase(phase, baseline_by_check):
                return False

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
