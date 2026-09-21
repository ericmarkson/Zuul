"""Audit -> plan generation -- FRD PLAN-1 path (a). Grouping is category (here: remediation
tag) plus declared-path overlap only, a purely lexical operation -- PLAN-2's v1 scope, unchanged
by the 2026-09-20 pivot. What changed: authoring each group's `side_effect_class`, description,
any scope beyond the findings' own `affected_paths`, and check set is no longer a fixed
node-template lookup -- it's one `plangen_llm.propose_phase` model call per group. This module
stays domain-agnostic: it reads the generic findings-file contract (category / severity /
affected_paths / remediation_tag) and calls out to a model provider, neither of which is
pack-specific code. It has no knowledge of .NET, csproj files, or any other domain content."""

from __future__ import annotations

import json
from pathlib import Path

from controlplane import plangen_llm
from controlplane.eventlog import DiagnosticLog
from controlplane.model_provider import ModelProvider

ANCHOR_CATEGORIES = ("project-format", "target-framework", "package-management", "incompatible-api")


def load_findings_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _project_dirs(findings: list[dict]) -> set[str]:
    """Every finding whose category is project-anchored (as opposed to a bare file scan, like
    config-format) always lists the owning .csproj among its affected_paths. Collecting those
    gives the set of project directories to overlap other findings' paths against -- lexical,
    not semantic: no parsing of what a project actually contains."""
    dirs = set()
    for f in findings:
        if f["category"] in ANCHOR_CATEGORIES:
            for p in f["affected_paths"]:
                if p.endswith(".csproj"):
                    dirs.add(Path(p).parent.as_posix())
    return dirs


def _component_for(finding: dict, project_dirs: set[str]) -> str:
    primary = finding["affected_paths"][0]
    best = None
    for d in project_dirs:
        if primary == d or primary.startswith(d + "/"):
            if best is None or len(d) > len(best):
                best = d
    return best or "(repo-root)"


def generate_phases(findings_document: dict, model_provider: ModelProvider, check_set: list[dict], max_output_tokens: int = 4000, max_tool_rounds: int = 8, diag_log: DiagnosticLog | None = None, mcp_servers: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """Returns (phases, dropped_finding_ids). A finding with no remediation_tag is
    informational -- there is nothing to group it into a phase for -- and is dropped from the
    plan, but never silently: its id is returned so the caller can record it, matching the
    project's own rule that nothing gets skipped without a trace (AUDIT-1's FINDING_DISCARDED
    precedent, even though this is a different case -- informational, not invalid).

    Each group gets one `plangen_llm.propose_phase` research-and-propose loop, with read-only
    access to the actual `target_repo` the findings document names, so a mis-scoped finding isn't
    the only signal the model has to work from. The proposal's `additional_scope` is unioned into
    the phase's `declared_scope` alongside the group's own `affected_paths` -- so the model is
    actually *permitted* to create what it proposes, not just told to -- and any proposed checks
    are appended to the plan's default check set (PLAN-5)."""
    findings = findings_document["findings"]
    target_repo = Path(findings_document["target_repo"])
    project_dirs = _project_dirs(findings)

    groups: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    dropped: list[str] = []

    for f in findings:
        tag = f.get("remediation_tag")
        if not tag:
            dropped.append(f["id"])
            continue
        component = _component_for(f, project_dirs)
        key = (tag, component)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)

    phases = []
    for n, key in enumerate(order, start=1):
        tag, component = key
        group = groups[key]

        proposal = plangen_llm.propose_phase(model_provider, tag, component, group, check_set, target_repo, max_output_tokens=max_output_tokens, max_tool_rounds=max_tool_rounds, diag_log=diag_log, mcp_servers=mcp_servers)

        affected_paths = sorted({p for f in group for p in f["affected_paths"]})
        finding_ids = sorted(f["id"] for f in group)

        check_fixtures = plangen_llm.materialize_fixtures(proposal.checks) if proposal.checks else []
        fixture_paths = {f["path"] for f in check_fixtures}
        # A fixture path must never end up in declared_scope, no matter what the model's own
        # additional_scope said -- it has to stay outside the implementer's writable scope for
        # INTEGRITY-3 to protect it automatically. Enforced here in code, not left to the prompt.
        declared_scope = sorted((set(affected_paths) | set(proposal.additional_scope)) - fixture_paths)

        checks = list(check_set) + [plangen_llm.materialize_check(c) for c in proposal.checks] if proposal.checks else None

        phases.append({
            "id": f"phase-{n}-{tag}",
            "description": f"[{tag}] {proposal.description} (findings: {', '.join(finding_ids)})",
            "declared_scope": declared_scope,
            "side_effect_class": proposal.side_effect_class,
            "edits": [],
            "checks": checks,
            "check_fixtures": check_fixtures,
        })

    return phases, dropped


def generate_plan(findings_path: Path, model_provider: ModelProvider, check_set: list[dict], run_id_prefix: str, max_output_tokens: int = 4000, max_tool_rounds: int = 8, diag_log: DiagnosticLog | None = None, mcp_servers: list[dict] | None = None) -> dict:
    document = load_findings_file(findings_path)
    phases, dropped = generate_phases(document, model_provider, check_set, max_output_tokens=max_output_tokens, max_tool_rounds=max_tool_rounds, diag_log=diag_log, mcp_servers=mcp_servers)

    description = (
        f"Generated {document['generated_at']} from '{document['pack']}' audit of "
        f"{document['target_repo']} (pack_content_hash {document['pack_content_hash'][:16]}...). "
        f"{len(phases)} phase(s) from {len(document['findings'])} finding(s). "
        "Every phase's edits are empty by design -- this generator only groups findings into "
        "phases (PLAN-1/PLAN-2 v1 scope, category + declared-path overlap only) and asks a "
        "model to research the target repo and propose each phase's scope/side-effect-class/"
        "checks; literal remediation content requires either hand-authoring or an LLM "
        "implementer (Phase E)."
    )
    if dropped:
        description += f" Findings with no remediation_tag were excluded, not silently: {', '.join(sorted(dropped))}."

    return {
        "schema_version": "0.1",
        "run_id_prefix": run_id_prefix,
        "plan_description": description,
        "check_set": check_set,
        "phases": phases,
        "_generated_from": {
            "findings_file": str(findings_path),
            "dropped_informational_findings": sorted(dropped),
        },
    }


def write_plan_file(path: Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
