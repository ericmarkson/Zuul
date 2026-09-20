"""LLM-driven phase authoring -- the 2026-09-20 pivot (point 1), extended the same day into a
bounded research loop rather than a single one-shot call. Supersedes the fixed node-template
catalogue that `plangen.py` used through commit `b25eda5`: instead of matching a finding group's
remediation tag against a hand-authored template file, one research-and-propose loop per group
proposes the phase's `side_effect_class`, a description, any scope beyond the findings' own
`affected_paths` the remediation will need, and whatever check(s) would actually prove *this
specific* remediation happened.

Why a research loop and not just a bigger one-shot prompt: Phase F's third run found that
`analyzer.py`'s static findings are necessarily incomplete -- its `.cs`-only usage-site detection
has no `.cshtml` equivalent, and the next gap will be some other file type nobody hardcoded a
scanner for. Patching the analyzer's extension list every time is hardcoding wearing a disguise.
The generalizable fix has to live here, not in the analyzer and not in the implementer: `PLAN-5`
freezes each phase's `declared_scope` at the approval gate, so any research into "where does this
finding's pattern actually show up" has to happen *before* that freeze to be actionable -- research
injected into the implementer's loop after the gate can only help it avoid a scope violation, it
can never let it actually finish a remediation whose true scope was mis-declared. So this module
gets the same kind of bounded tool-calling loop `llm_implementer.py` has, with read-only tools
that let the model independently search the actual target repo (`grep_repo`, `list_directory`,
`read_file`, shared via `repo_tools.py`) before committing to a proposal -- generalized to any
file type or remediation category the model decides to check, not enumerated in advance.

FRD QA-2 stays non-negotiable throughout: the model authors a check's content (a Python script)
at generation time, but the check is still executed as a subprocess and still verified by exit
code alone, at execution time, by the same unmodified `checks.py` every other check goes through.
The model never gets to declare its own verdict -- only what command to run, and only what scope
to declare. Nothing here pre-filters `side_effect_class` or `additional_scope` against the
findings' own paths, mirroring `llm_implementer.py`'s "detection, not prevention" stance --
INTEGRITY-3's post-commit scope diff is what actually enforces a phase's declared scope at
execution time; this module is not that enforcement, just an input to it, reviewed by the
operator at the gate before anything executes."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from controlplane import repo_tools
from controlplane.model_provider import ModelProvider

SIDE_EFFECT_CLASSES = ("file-only", "package-manager-mutating", "external-service-call")

SYSTEM_PROMPT = """You are the plan-generation agent inside an autonomous, git-native code \
migration control plane. You are given one group of related findings from a static-analysis \
audit -- findings that share a remediation category and a project/component -- and must propose \
how the phase that remediates them should be governed and verified. You do NOT write the \
remediation code itself; a separate implementer agent does that later, against whatever scope \
and checks you declare here.

The static analyzer that produced these findings has known blind spots -- it may only scan \
certain file types or patterns, so real usage sites relevant to this remediation can exist in \
files the findings never mention (e.g. a Razor view, a resource file, a config transform, a \
different assembly). Before finalizing, use your tools to check whether that is true here:
- grep_repo(pattern, path_glob): search file contents across the actual target repository for a \
literal substring (case-insensitive), optionally restricted to a glob such as "**/*.cshtml". Use \
this to look for the finding's specific API names, type names, or config keys in file types the \
findings don't already cover.
- list_directory(path): list a directory's entries, to discover related files by name. Use "." \
for the repository root.
- read_file(path): read a specific file's contents once you've found something worth inspecting.
- finalize_proposal(...): submit your final proposal. Call this exactly once, when you are done \
researching (which may be immediately, for a finding category too simple to need it).

finalize_proposal's fields:
- side_effect_class: exactly one of "file-only", "package-manager-mutating", \
"external-service-call" -- reflecting how reversible this phase's remediation is.
- description: a clear, specific description of what this phase should accomplish.
- additional_scope: repo-relative paths beyond the findings' own affected_paths that the \
remediation will plausibly need to create or modify -- including anything your own research \
turned up that the findings missed. Empty list if none.
- checks: a list of {"id": "...", "python_script": "..."} -- a self-contained Python 3 script per \
check, run via `python -c <script>` with the verifier's checked-out repo as the working \
directory, that exits 0 if and only if this specific remediation actually happened -- or null if \
the plan's default build/test check set is already sufficient, with nothing phase-specific worth \
checking.

Rules:
- Research is most valuable for findings whose category a narrow static scanner could plausibly \
miss (API/type usage, cross-file references) -- it may be unnecessary for something like a single \
well-defined project-format finding with no ambiguity about what needs to change.
- Use your tools sparingly and purposefully -- you have a bounded number of tool-call rounds.
- "checks" being null is a real, correct answer when the plan's default check set already proves \
the remediation -- do not invent a check just to have one.
- You must call finalize_proposal to complete this task. Do not describe a proposal in plain text \
instead of calling it.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "grep_repo",
            "description": "Search file contents across the target repository for a literal, case-insensitive substring, to find usage sites the audit findings might not have covered.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text to search for."},
                    "path_glob": {"type": "string", "description": "Optional glob to restrict the search, e.g. '**/*.cshtml'. Defaults to all files."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the entries of a directory in the target repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "repo-relative directory path, or '.' for the repo root"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the current contents of a file in the target repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "repo-relative file path"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_proposal",
            "description": "Submit the final phase proposal. Call exactly once, after any research.",
            "parameters": {
                "type": "object",
                "properties": {
                    "side_effect_class": {"type": "string", "enum": list(SIDE_EFFECT_CLASSES)},
                    "description": {"type": "string"},
                    "additional_scope": {"type": "array", "items": {"type": "string"}},
                    "checks": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "python_script": {"type": "string"},
                            },
                            "required": ["id", "python_script"],
                        },
                    },
                },
                "required": ["side_effect_class", "description", "additional_scope", "checks"],
            },
        },
    },
]


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


def _execute_tool(name: str, arguments: dict, target_repo: Path) -> str:
    if name == "grep_repo":
        return repo_tools.grep_repo_tool(target_repo, arguments.get("pattern", ""), arguments.get("path_glob"))
    if name == "read_file":
        return repo_tools.read_file_tool(target_repo, arguments.get("path", ""))
    if name == "list_directory":
        return repo_tools.list_directory_tool(target_repo, arguments.get("path", "."))
    return f"error: unknown tool {name!r}"


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


def _parse_proposal(arguments: dict) -> PhaseProposal:
    if not isinstance(arguments, dict):
        raise MalformedPlanProposal(f"finalize_proposal arguments were not an object: {arguments!r}")

    side_effect_class = arguments.get("side_effect_class")
    if side_effect_class not in SIDE_EFFECT_CLASSES:
        raise MalformedPlanProposal(f"'side_effect_class' must be one of {SIDE_EFFECT_CLASSES}, got {side_effect_class!r}")

    description = arguments.get("description")
    if not isinstance(description, str) or not description.strip():
        raise MalformedPlanProposal(f"'description' must be a non-empty string, got {description!r}")

    additional_scope = arguments.get("additional_scope", [])
    if not isinstance(additional_scope, list) or not all(isinstance(p, str) for p in additional_scope):
        raise MalformedPlanProposal(f"'additional_scope' must be a list of strings, got {additional_scope!r}")

    checks = _validate_checks(arguments.get("checks"))

    return PhaseProposal(side_effect_class=side_effect_class, description=description, additional_scope=additional_scope, checks=checks)


def propose_phase(
    provider: ModelProvider,
    remediation_tag: str,
    component: str,
    findings: list[dict],
    plan_check_set: list[dict],
    target_repo: Path,
    max_output_tokens: int = 4000,
    max_tool_rounds: int = 8,
) -> PhaseProposal:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(remediation_tag, component, findings, plan_check_set)},
    ]

    for round_num in range(1, max_tool_rounds + 1):
        response = provider.complete_with_tools(messages, max_output_tokens, TOOLS)

        if not response.tool_calls:
            raise MalformedPlanProposal(
                f"round {round_num}: model responded without calling any tool (must call finalize_proposal): {response.content!r}"
            )

        messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls],
        })

        finalize_call = next((tc for tc in response.tool_calls if tc.name == "finalize_proposal"), None)
        if finalize_call is not None:
            return _parse_proposal(finalize_call.arguments)

        for tc in response.tool_calls:
            result = _execute_tool(tc.name, tc.arguments, target_repo)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    raise MalformedPlanProposal(f"plan generator did not call finalize_proposal within {max_tool_rounds} tool-call round(s)")


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
