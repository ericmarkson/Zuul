"""The LLM-driven implementer -- Phase E, made agentic by the 2026-09-20 pivot (point 2). Given
a phase whose plan carries no pre-authored edits (the audit-derived path, Phase D), runs a
bounded tool-calling loop: the model may call read-only context tools (read_file,
list_directory) before finalizing, then must call finalize_edits exactly once to submit its
proposed full file contents for paths within its declared scope.

FRD EXEC-2 stays honest here: this module hands the model no file-write tools of its own -- only
finalize_edits, which returns a parsed proposal; the runner is what writes files to disk,
commits, and lets INTEGRITY-3's post-commit scope diff be the actual enforcement, exactly the
same path a scripted implementer's mistakes already go through (Phase A's phase-3 demo). Nothing
here pre-filters what the model is allowed to propose; detection, not prevention, is the
mechanism, by design. The read-only tools ARE confined to the target repo (a path-traversal
guard, not a scope guard) -- there is no reason for the implementer to ever read outside the
repo it was handed, and no governance value in letting it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from controlplane.model_provider import ModelProvider

SYSTEM_PROMPT = """You are the implementer agent inside an autonomous, git-native code \
migration control plane. You are given exactly one phase of a larger plan: a description, a \
declared scope (the only paths you may reasonably touch), the current contents of any files in \
that scope that already exist, and the command(s) that will verify your work afterward.

You have tools available:
- read_file(path): read the current contents of any file in the target repository, for context \
beyond what's already shown (e.g. a file referenced by, but not itself part of, the declared \
scope).
- list_directory(path): list the entries of a directory in the target repository, to discover \
related files you don't already know the name of. Use "." for the repository root.
- finalize_edits(edits): submit your final, complete set of file edits. Call this exactly once, \
when you are done gathering any context you need. Each edit's "content" is the COMPLETE new \
content of that file (not a diff or partial snippet) -- it will overwrite the entire file. If a \
listed path does not exist yet, propose it as a new file. To DELETE an existing file, submit its \
path with "content" set to JSON null -- not an empty string, which would just replace it with an \
empty file instead of removing it.

Rules:
- Only include paths in finalize_edits that make sense for this specific phase's description. \
Do not "helpfully" touch anything outside what the phase describes, even if you notice other \
things that look wrong.
- Pay attention to the verification commands you're given -- if a check requires a legacy file \
to no longer exist, delete it (content: null) rather than leaving it in place after migrating \
its contents elsewhere.
- Use read_file/list_directory sparingly and only when genuinely useful -- you have a bounded \
number of tool-call rounds.
- You must call finalize_edits to complete this task. Do not describe edits in plain text \
instead of calling it.
"""

TOOLS = [
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
            "name": "finalize_edits",
            "description": "Submit the final set of file edits for this phase. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {
                                    "type": ["string", "null"],
                                    "description": "Full new file content, or null to delete an existing file at this path.",
                                },
                            },
                            "required": ["path", "content"],
                        },
                    }
                },
                "required": ["edits"],
            },
        },
    },
]


@dataclass(frozen=True)
class ProposedEdit:
    path: str
    content: str | None  # None means "delete this file" -- see finalize_edits' tool description


@dataclass(frozen=True)
class ImplementerResult:
    edits: list[ProposedEdit]
    input_tokens: int
    output_tokens: int


class MalformedResponse(RuntimeError):
    pass


def _read_existing(target_repo: Path, declared_scope: list[str]) -> dict[str, str | None]:
    existing = {}
    for rel_path in declared_scope:
        abs_path = target_repo / rel_path
        if abs_path.is_file():
            existing[rel_path] = abs_path.read_text(encoding="utf-8", errors="replace")
        else:
            existing[rel_path] = None
    return existing


def build_user_prompt(
    phase_description: str,
    declared_scope: list[str],
    target_repo: Path,
    check_commands: list[list[str]],
    prior_failure_feedback: str | None = None,
) -> str:
    existing = _read_existing(target_repo, declared_scope)
    lines = [
        f"Phase description: {phase_description}",
        f"Declared scope: {declared_scope}",
        f"Verification commands that will run afterward: {check_commands}",
        "",
        "Current contents of files in scope:",
    ]
    for rel_path, content in existing.items():
        if content is None:
            lines.append(f"--- {rel_path} (does not exist yet) ---")
        else:
            lines.append(f"--- {rel_path} ---\n{content}")

    if prior_failure_feedback:
        lines.append("")
        lines.append("A previous attempt at this same phase failed verification. Feedback:")
        lines.append(prior_failure_feedback)
        lines.append("Produce a corrected set of edits.")

    return "\n".join(lines)


def _resolve_within_repo(target_repo: Path, rel_path: str) -> Path | None:
    """Path-traversal guard for the read-only tools -- None means "refuse," not "raise": a
    misbehaving tool call should come back as an error string the model can react to, not blow
    up the whole loop."""
    candidate = (target_repo / rel_path).resolve()
    repo_root = target_repo.resolve()
    if candidate != repo_root and repo_root not in candidate.parents:
        return None
    return candidate


def _execute_tool(name: str, arguments: dict, target_repo: Path) -> str:
    if name == "read_file":
        resolved = _resolve_within_repo(target_repo, arguments.get("path", ""))
        if resolved is None:
            return "error: path is outside the target repository"
        if not resolved.is_file():
            return "error: no such file"
        return resolved.read_text(encoding="utf-8", errors="replace")
    if name == "list_directory":
        resolved = _resolve_within_repo(target_repo, arguments.get("path", "."))
        if resolved is None:
            return "error: path is outside the target repository"
        if not resolved.is_dir():
            return "error: no such directory"
        return "\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in resolved.iterdir()))
    return f"error: unknown tool {name!r}"


def _parse_finalize_edits(arguments: dict) -> list[ProposedEdit]:
    if not isinstance(arguments, dict) or "edits" not in arguments or not isinstance(arguments["edits"], list):
        raise MalformedResponse(f"finalize_edits call missing a top-level 'edits' list: {arguments!r}")
    edits = []
    for i, item in enumerate(arguments["edits"]):
        if not isinstance(item, dict) or "path" not in item or "content" not in item:
            raise MalformedResponse(f"edits[{i}] missing 'path' or 'content': {item!r}")
        content = item["content"]
        if content is not None and not isinstance(content, str):
            raise MalformedResponse(f"edits[{i}]['content'] must be a string or null (for deletion), got {content!r}")
        edits.append(ProposedEdit(path=item["path"], content=content))
    if not edits:
        raise MalformedResponse("finalize_edits call had zero edits")
    return edits


def request_edits(
    provider: ModelProvider,
    phase_description: str,
    declared_scope: list[str],
    target_repo: Path,
    check_commands: list[list[str]],
    max_output_tokens: int,
    prior_failure_feedback: str | None = None,
    max_tool_rounds: int = 6,
) -> ImplementerResult:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(phase_description, declared_scope, target_repo, check_commands, prior_failure_feedback)},
    ]
    input_tokens = 0
    output_tokens = 0

    for round_num in range(1, max_tool_rounds + 1):
        response = provider.complete_with_tools(messages, max_output_tokens, TOOLS)
        input_tokens += response.input_tokens
        output_tokens += response.output_tokens

        if not response.tool_calls:
            raise MalformedResponse(
                f"round {round_num}: model responded without calling any tool (must call finalize_edits): {response.content!r}"
            )

        messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls],
        })

        finalize_call = next((tc for tc in response.tool_calls if tc.name == "finalize_edits"), None)
        if finalize_call is not None:
            edits = _parse_finalize_edits(finalize_call.arguments)
            return ImplementerResult(edits=edits, input_tokens=input_tokens, output_tokens=output_tokens)

        for tc in response.tool_calls:
            result = _execute_tool(tc.name, tc.arguments, target_repo)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    raise MalformedResponse(f"implementer did not call finalize_edits within {max_tool_rounds} tool-call round(s)")
