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

FRD QA-2 stays non-negotiable throughout: the model authors a check's command (and, since the
same day's later extension, any supporting files that command needs to exist) at generation
time, but the check is still executed as a subprocess and still verified by exit code alone, at
execution time, by the same unmodified `checks.py` every other check goes through. The model
never gets to declare its own verdict -- only what command to run, and only what scope to
declare. Nothing here pre-filters `side_effect_class` or `additional_scope` against the findings'
own paths, mirroring `llm_implementer.py`'s "detection, not prevention" stance -- INTEGRITY-3's
post-commit scope diff is what actually enforces a phase's declared scope at execution time; this
module is not that enforcement, just an input to it, reviewed by the operator at the gate before
anything executes.

A check's `command` is a fully generic subprocess argv -- not hardcoded to Python. A model-
authored check was originally always wrapped as `python -c <script>`, which quietly assumed
every check was expressible as a self-contained Python one-liner; that assumption breaks for a
check that needs to actually compile and run the migrated code (e.g. `dotnet test`), which is
exactly what closes the gap a text-only check cannot: a check that greps final source for a
class name is satisfied equally by a real port and by a hollow stub with the right name and no
real logic (found live, 2026-09-20, phase-3's `RegisterController` reduced to an empty shell that
still matched its own survival check). A behavioral check that compiles and runs the code cannot
be satisfied by a stub. `command` can be anything; a check that needs a supporting test file to
exist declares it via `supporting_files`, materialized by the runner *before* the phase's own
attempt loop begins and deliberately kept outside `declared_scope` -- so it is present when the
implementer starts (visible to it like any other file, via `read_file`), but `INTEGRITY-3`
automatically treats any attempt to modify it as a scope violation, the same unmodified mechanism
that already protects everything else, with no new enforcement code required."""

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
turned up that the findings missed. Empty list if none. Never include a path you also list in a \
check's own supporting_files (see below) -- those are frozen and must not be in scope.
- checks: a list of {"id": "...", "command": [...], "supporting_files": [...]} -- or null if the \
plan's default build/test check set is already sufficient, with nothing phase-specific worth \
checking. For each check:
  - command: a subprocess argv (list of strings), run with the verifier's checked-out repo as \
the working directory, that exits 0 if and only if this specific remediation actually happened. \
Use whatever tool actually fits -- there is no required language. For a simple, self-contained \
inline script, use the literal token "{python}" as the first element (it is substituted with the \
right interpreter at run time), e.g. ["{python}", "-c", "<script>"]. For a real compiled/executed \
check (e.g. `dotnet test some.Tests.csproj`), use that tool's own command directly.
  - supporting_files: a list of {"path": "...", "content": "..."} for any file that command needs \
to already exist to run (most commonly a test source file) -- empty list if the command is \
self-contained. These are created before the implementer's phase even begins and are never part \
of its declared scope; do not also list their paths in additional_scope.

A check that only proves a forbidden pattern is GONE can be satisfied just as easily by deleting \
the code that used it as by actually porting it -- deletion is often the cheaper path for an \
implementer facing a hard rewrite, and a check built from reading text (even a check that greps \
for a class name) cannot tell a real implementation from an empty shell with the right name and \
no real logic. Before finalizing, decide honestly which kind of phase this is:
- A REMOVAL phase, where a file or setting is meant to disappear with no successor (e.g. a \
legacy file superseded by a replacement already covered by its own existence check) -- absence \
is genuinely the correct, sufficient proof here.
- A TRANSFORM phase, where existing behavior is meant to survive in a new form (e.g. rewriting \
source files to a new API rather than deleting the functionality they implement) -- for these, \
prefer a BEHAVIORAL check over a text-inspection one whenever the repository's own toolchain \
makes it feasible: research (read_file/grep_repo) what the current code actually does, then \
write a real test (via supporting_files) that exercises the migrated code's behavior and asserts \
on it, run through the repository's actual test tooling (whatever you find it uses, or a minimal \
ad hoc one if it uses none) -- not merely a script that checks a name or pattern is present or \
absent. A check that compiles and runs the code cannot be satisfied by a hollow stub the way a \
text-pattern check can. This generalizes to any language, file type, or test framework; it is \
not specific to any one ecosystem's concepts, and the choice of tool is yours to make from what \
you find in the repository.

Rules:
- Research is most valuable for findings whose category a narrow static scanner could plausibly \
miss (API/type usage, cross-file references) -- it may be unnecessary for something like a single \
well-defined project-format finding with no ambiguity about what needs to change.
- Use your tools sparingly and purposefully -- you have a bounded number of tool-call rounds.
- "checks" being null is a real, correct answer when the plan's default check set already proves \
the remediation -- do not invent a check just to have one.
- For a TRANSFORM phase, you MUST include at least one check that positively confirms real \
content survived, not solely a check that the old pattern is gone -- and prefer a behavioral \
check (one that actually runs the migrated code) over a text-inspection one when feasible.
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
                                "command": {"type": "array", "items": {"type": "string"}},
                                "supporting_files": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "path": {"type": "string"},
                                            "content": {"type": "string"},
                                        },
                                        "required": ["path", "content"],
                                    },
                                },
                            },
                            "required": ["id", "command", "supporting_files"],
                        },
                    },
                },
                "required": ["side_effect_class", "description", "additional_scope", "checks"],
            },
        },
    },
]


@dataclass(frozen=True)
class SupportingFile:
    path: str
    content: str


@dataclass(frozen=True)
class CheckProposal:
    id: str
    command: list[str]
    supporting_files: list[SupportingFile]


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


def _validate_inline_python_syntax(check_id: str, command: list[str]) -> None:
    """Best-effort syntax pre-check for the common "{python}" -c <script>" shape -- a real
    failure mode found live, 2026-09-20: a check that doesn't even compile fails identically no
    matter what the implementer produces, silently wasting the phase's entire retry budget on an
    unwinnable check rather than a real content problem. Caught here, before the proposal is ever
    frozen into a plan. Deliberately does not (and cannot generically) validate any other tool's
    command -- a `dotnet test` invocation's C# correctness is discovered by its own exit code at
    check time, exactly like any other check; that's QA-2 working as intended, not a gap."""
    if command and command[0] == "{python}" and "-c" in command:
        idx = command.index("-c")
        if idx + 1 < len(command):
            script = command[idx + 1]
            try:
                compile(script, f"<check:{check_id}>", "exec")
            except SyntaxError as exc:
                raise MalformedPlanProposal(f"check {check_id!r}'s inline Python script does not compile: {exc}") from exc


def _validate_checks(raw_checks) -> list[CheckProposal] | None:
    if raw_checks is None:
        return None
    if not isinstance(raw_checks, list):
        raise MalformedPlanProposal(f"'checks' must be a list or null, got {raw_checks!r}")
    checks = []
    for i, item in enumerate(raw_checks):
        if not isinstance(item, dict) or "id" not in item or "command" not in item:
            raise MalformedPlanProposal(f"checks[{i}] missing 'id' or 'command': {item!r}")
        command = item["command"]
        if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
            raise MalformedPlanProposal(f"checks[{i}] 'command' must be a non-empty list of strings, got {command!r}")
        _validate_inline_python_syntax(item["id"], command)

        raw_files = item.get("supporting_files", [])
        if not isinstance(raw_files, list):
            raise MalformedPlanProposal(f"checks[{i}] 'supporting_files' must be a list, got {raw_files!r}")
        supporting_files = []
        for j, f in enumerate(raw_files):
            if not isinstance(f, dict) or "path" not in f or "content" not in f:
                raise MalformedPlanProposal(f"checks[{i}].supporting_files[{j}] missing 'path' or 'content': {f!r}")
            supporting_files.append(SupportingFile(path=f["path"], content=f["content"]))

        checks.append(CheckProposal(id=item["id"], command=command, supporting_files=supporting_files))
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
        proposal: PhaseProposal | None = None
        if finalize_call is not None:
            try:
                proposal = _parse_proposal(finalize_call.arguments)
            except MalformedPlanProposal as exc:
                if round_num >= max_tool_rounds:
                    raise
                # Give the model a chance to self-correct within the same bounded loop, the same
                # way EXEC-3's retry loop feeds implementer failures back -- a malformed proposal
                # (including a check script that doesn't compile) is exactly the kind of mistake
                # a model can fix immediately once told what's wrong, cheaper than failing the
                # whole generation and starting over.
                messages.append({
                    "role": "tool", "tool_call_id": finalize_call.id,
                    "content": f"error: your proposal was invalid: {exc}. Call finalize_proposal again with a corrected proposal.",
                })

        # Every other tool call in this batch still needs a response before the next request,
        # regardless of whether finalize_proposal (if also called this round) succeeded, failed,
        # or wasn't called at all -- the API requires one tool-role message per tool call.
        for tc in response.tool_calls:
            if tc is finalize_call:
                continue
            result = _execute_tool(tc.name, tc.arguments, target_repo)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if proposal is not None:
            return proposal

    raise MalformedPlanProposal(f"plan generator did not call finalize_proposal within {max_tool_rounds} tool-call round(s)")


def materialize_check(check: CheckProposal) -> dict:
    """A model-authored check becomes an ordinary CheckSpec-shaped dict: a subprocess command
    whose exit code governs (QA-2), exactly like every hand-authored or template-authored check
    before it. Only *who wrote the command* is new. "{python}" is the one placeholder resolved
    here rather than left for `runner.py`'s generic substitution, since it names a fact about
    this machine (which interpreter this control plane is running under) rather than anything
    about a specific run or phase."""
    command = [sys.executable if part == "{python}" else part for part in check.command]
    return {
        "id": check.id,
        "command": command,
        "result_artifact": "{run_dir}/results/{phase_id}/" + check.id + "-unused.xml",
        "result_format": "junit",
    }


def materialize_fixtures(checks: list[CheckProposal]) -> list[dict]:
    """Collects every check's supporting_files into the flat {"path", "content"} list
    `runner.py` writes and commits *before* a phase's own attempt loop begins -- so they exist
    when the implementer starts (visible like any other file) but are never part of its
    declared_scope, and INTEGRITY-3's unmodified post-commit scope diff automatically protects
    them from being altered, without any new enforcement mechanism."""
    fixtures: dict[str, str] = {}
    for check in checks:
        for f in check.supporting_files:
            fixtures[f.path] = f.content
    return [{"path": path, "content": content} for path, content in fixtures.items()]
