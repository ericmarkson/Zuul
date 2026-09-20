"""The LLM-driven implementer -- Phase E. Given a phase whose plan carries no pre-authored
edits (the audit-derived path, Phase D), asks the model to propose full file contents for paths
within its declared scope, within its check set.

FRD EXEC-2 stays honest here: this module hands the model no file-write tools of its own -- it
returns a parsed proposal, and the runner is what writes files to disk, commits, and lets
INTEGRITY-3's post-commit scope diff be the actual enforcement, exactly the same path a
scripted implementer's mistakes already go through (Phase A's phase-3 demo). Nothing here
pre-filters what the model is allowed to propose; detection, not prevention, is the mechanism,
by design."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from controlplane.model_provider import ModelProvider

SYSTEM_PROMPT = """You are the implementer agent inside an autonomous, git-native code \
migration control plane. You are given exactly one phase of a larger plan: a description, a \
declared scope (the only paths you may reasonably touch), the current contents of any files in \
that scope that already exist, and the command(s) that will verify your work afterward.

Respond with a single JSON object and nothing else: {"edits": [{"path": "<repo-relative path>", \
"content": "<the COMPLETE new content of that file>"}]}

Rules:
- "content" is the full replacement content of the file, not a diff or a partial snippet -- it \
will overwrite the entire file.
- Only include paths that make sense for this specific phase's description. Do not "helpfully" \
touch anything outside what the phase describes, even if you notice other things that look wrong.
- If a listed path does not exist yet, propose it as a new file.
- Do not include explanations, markdown fences, or any text outside the JSON object.
"""


@dataclass(frozen=True)
class ProposedEdit:
    path: str
    content: str


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


def request_edits(
    provider: ModelProvider,
    phase_description: str,
    declared_scope: list[str],
    target_repo: Path,
    check_commands: list[list[str]],
    max_output_tokens: int,
    prior_failure_feedback: str | None = None,
) -> ImplementerResult:
    user_prompt = build_user_prompt(phase_description, declared_scope, target_repo, check_commands, prior_failure_feedback)
    response = provider.complete(SYSTEM_PROMPT, user_prompt, max_output_tokens)

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise MalformedResponse(f"response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict) or "edits" not in parsed or not isinstance(parsed["edits"], list):
        raise MalformedResponse(f"response JSON missing a top-level 'edits' list: {parsed!r}")

    edits = []
    for i, item in enumerate(parsed["edits"]):
        if not isinstance(item, dict) or "path" not in item or "content" not in item:
            raise MalformedResponse(f"edits[{i}] missing 'path' or 'content': {item!r}")
        edits.append(ProposedEdit(path=item["path"], content=item["content"]))

    if not edits:
        raise MalformedResponse("response had zero edits")

    return ImplementerResult(edits=edits, input_tokens=response.input_tokens, output_tokens=response.output_tokens)
