"""LLM-driven phase authoring -- the 2026-09-20 pivot (point 1). Supersedes the fixed
node-template catalogue that `plangen.py` used through commit `b25eda5`: instead of matching a
finding group's remediation tag against a hand-authored template file, one model call per group
proposes the phase's `side_effect_class`, a description, any scope beyond the findings' own
`affected_paths` the remediation will need, and whatever check(s) would actually prove *this
specific* remediation happened.

FRD QA-2 stays non-negotiable here: the model authors a check's content (a Python script) at
generation time, but the check is still executed as a subprocess and still verified by exit code
alone, at execution time, by the same unmodified `checks.py` every other check goes through. The
model never gets to declare its own verdict -- only what command to run. Nothing here pre-filters
`side_effect_class` or `additional_scope` against the findings' own paths, mirroring
`llm_implementer.py`'s "detection, not prevention" stance -- INTEGRITY-3's post-commit scope diff
is what actually enforces a phase's declared scope at execution time; this module is not that
enforcement, just an input to it, reviewed by the operator at the gate before anything executes."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from controlplane.model_provider import ModelProvider

SIDE_EFFECT_CLASSES = ("file-only", "package-manager-mutating", "external-service-call")

SYSTEM_PROMPT = """You are the plan-generation agent inside an autonomous, git-native code \
migration control plane. You are given one group of related findings from a static-analysis \
audit -- findings that share a remediation category and a project/component -- and must propose \
how the phase that remediates them should be governed and verified. You do NOT write the \
remediation code itself; a separate implementer agent does that later, against whatever scope \
and checks you declare here.

Respond with a single JSON object and nothing else:
{
  "side_effect_class": "file-only" | "package-manager-mutating" | "external-service-call",
  "description": "<a clear, specific description of what this phase should accomplish>",
  "additional_scope": ["<repo-relative paths beyond the findings' own affected_paths that the \
remediation will plausibly need to create or modify, e.g. a new config file replacing a legacy \
one -- empty list if none>"],
  "checks": [{"id": "<short-id>", "python_script": "<a self-contained Python 3 script, run via \
`python -c <script>` with the verifier's checked-out repo as the working directory, that exits 0 \
if and only if this specific remediation actually happened (e.g. a new file exists and is \
non-empty, an old file no longer references a removed API, a project file's target framework \
was actually changed) -- or null if the plan's default build/test check set is already \
sufficient to prove this remediation, with nothing phase-specific worth checking beyond that>"]
}

Rules:
- side_effect_class must be exactly one of the three listed values, reflecting how reversible \
this phase's remediation is: file-only if it's purely a source/config edit, \
package-manager-mutating if it invokes a package manager, external-service-call if it makes a \
live call to an external system.
- "checks" being null is a real, correct answer when the plan's default check set already \
proves the remediation -- do not invent a check just to have one.
- Do not include explanations, markdown fences, or any text outside the JSON object.
"""


@dataclass(frozen=True)
class CheckProposal:
    id: str
    python_script: str


@dataclass(frozen=True)
class PhaseProposal:
    side_effect_class: str
    description: str
    additional_scope: list[str]
    checks: list[CheckProposal] | None


class MalformedPlanProposal(RuntimeError):
    pass


def build_user_prompt(remediation_tag: str, component: str, findings: list[dict], plan_check_set: list[dict]) -> str:
    lines = [
        f"Remediation tag: {remediation_tag}",
        f"Component/project: {component}",
        f"The plan's default check set (always runs regardless of what you propose): {[c['id'] for c in plan_check_set]}",
        "",
        "Findings in this group:",
    ]
    for f in findings:
        lines.append(json.dumps({
            "id": f["id"], "category": f["category"], "severity": f.get("severity"),
            "affected_paths": f["affected_paths"], "description": f["description"],
            "evidence": f.get("evidence", {}),
        }))
    return "\n".join(lines)


def _validate_checks(raw_checks) -> list[CheckProposal] | None:
    if raw_checks is None:
        return None
    if not isinstance(raw_checks, list):
        raise MalformedPlanProposal(f"'checks' must be a list or null, got {raw_checks!r}")
    checks = []
    for i, item in enumerate(raw_checks):
        if not isinstance(item, dict) or "id" not in item or "python_script" not in item:
            raise MalformedPlanProposal(f"checks[{i}] missing 'id' or 'python_script': {item!r}")
        checks.append(CheckProposal(id=item["id"], python_script=item["python_script"]))
    return checks or None


def propose_phase(
    provider: ModelProvider,
    remediation_tag: str,
    component: str,
    findings: list[dict],
    plan_check_set: list[dict],
    max_output_tokens: int = 4000,
) -> PhaseProposal:
    user_prompt = build_user_prompt(remediation_tag, component, findings, plan_check_set)
    response = provider.complete(SYSTEM_PROMPT, user_prompt, max_output_tokens)

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise MalformedPlanProposal(f"response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise MalformedPlanProposal(f"response JSON was not an object: {parsed!r}")

    side_effect_class = parsed.get("side_effect_class")
    if side_effect_class not in SIDE_EFFECT_CLASSES:
        raise MalformedPlanProposal(f"'side_effect_class' must be one of {SIDE_EFFECT_CLASSES}, got {side_effect_class!r}")

    description = parsed.get("description")
    if not isinstance(description, str) or not description.strip():
        raise MalformedPlanProposal(f"'description' must be a non-empty string, got {description!r}")

    additional_scope = parsed.get("additional_scope", [])
    if not isinstance(additional_scope, list) or not all(isinstance(p, str) for p in additional_scope):
        raise MalformedPlanProposal(f"'additional_scope' must be a list of strings, got {additional_scope!r}")

    checks = _validate_checks(parsed.get("checks"))

    return PhaseProposal(side_effect_class=side_effect_class, description=description, additional_scope=additional_scope, checks=checks)


def materialize_check(check: CheckProposal) -> dict:
    """A model-authored check becomes an ordinary CheckSpec-shaped dict: a subprocess command
    whose exit code governs (QA-2), exactly like every hand-authored or template-authored check
    before it. Only *who wrote the script* is new."""
    return {
        "id": check.id,
        "command": [sys.executable, "-c", check.python_script],
        "result_artifact": "{run_dir}/results/{phase_id}/" + check.id + "-unused.xml",
        "result_format": "junit",
    }
