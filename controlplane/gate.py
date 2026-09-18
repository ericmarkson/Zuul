"""The approval checkpoint — FRD APPROVAL-1 (contents), APPROVAL-5 (accept-all-or-abort, exactly
two responses), SECRET-1 (forced acknowledgment of findings before approval is even offered)."""

from __future__ import annotations

from controlplane.checks import CheckResult
from controlplane.plan import Plan
from controlplane.secrets_scan import SecretFinding

DISCLOSURE_POLICY = """\
Third-party data-disclosure policy (FRD DISCLOSE-1):
  Sent to a model provider, when one is used:
    the contents of files within the active phase's declared scope, the plan and phase
    description, the assessment findings for that phase, and check output excerpts on failure.
  Never sent:
    any file outside the active phase's declared scope; the diagnostic log (DIAG-1); any file
    matching SECRET-1's credential-path patterns, even inside a declared scope.
  Operator responsibility:
    confirm this repository is eligible for third-party disclosure under your organization's
    policy, confirm the provider's data-retention/training-use terms before configuring it, and
    do not run this system against a repository containing live secrets.
  This run: no third-party model provider is used. The implementer is a scripted, deterministic
    edit set checked into fixtures/sample-dotnet-app-edits/ (Phase A, no LLM in the loop)."""


def present_secret_findings(findings: list[SecretFinding]) -> None:
    print("-" * 70)
    print("SECRET SCAN (SECRET-1)")
    if not findings:
        print("  No findings.")
        return
    for finding in findings:
        print(f"  [{finding.kind}] {finding.path}: {finding.detail}")


def require_secret_acknowledgment(findings: list[SecretFinding], auto_approve: bool = False) -> bool:
    if not findings:
        return True
    print(f"\n{len(findings)} secret-scan finding(s) above. This run does not mask, remove, or")
    print("neutralize them — it only surfaces them. You are responsible for confirming this")
    print("repository is safe to run this system against.")
    if auto_approve:
        print("Acknowledge these findings and continue to the approval checkpoint? [y/N] y  (--yes)")
        return True
    answer = input("Acknowledge these findings and continue to the approval checkpoint? [y/N] ").strip().lower()
    return answer == "y"


def present_gate(plan: Plan, baseline_sha: str, baseline_results: list[CheckResult]) -> None:
    print("=" * 70)
    print("APPROVAL CHECKPOINT (APPROVAL-1)")
    print("=" * 70)
    print(f"Plan: {plan.source_path} (content hash {plan.content_hash[:16]}...)")
    print(f"Baseline commit: {baseline_sha}")
    print(f"\n{plan.plan_description}\n")
    print(f"Phases ({len(plan.phases)}):")
    for phase in plan.phases:
        print(f"  - {phase.id} [{phase.side_effect_class}]")
        print(f"      scope: {', '.join(phase.declared_scope)}")
        print(f"      checks: {', '.join(c.id for c in plan.check_set)}")
        print(f"      {phase.description}")
    print("\nBaseline check results (QA-5 — later phases are evaluated as deltas against this):")
    for result in baseline_results:
        failed = sorted(result.failed_tests)
        status = "no failures" if not failed else f"{len(failed)} pre-existing failure(s): {failed}"
        print(f"  - {result.check_id}: exit={result.exit_code}, {status}")
    print()
    print(DISCLOSURE_POLICY)
    print("-" * 70)


def ask_approval(auto_approve: bool = False) -> bool:
    if auto_approve:
        print("Approve this plan and begin unattended execution? [y/N] (accept-all-or-abort) y  (--yes)")
        return True
    answer = input("Approve this plan and begin unattended execution? [y/N] (accept-all-or-abort) ").strip().lower()
    return answer == "y"
