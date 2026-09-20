"""Audit -> plan generation -- FRD PLAN-1 path (a). Grouping is category (here: remediation
tag) plus declared-path overlap only, a purely lexical operation -- PLAN-2's v1 scope. This
module is domain-agnostic: it reads the generic findings-file contract (category / severity /
affected_paths / remediation_tag) and a directory of node-template JSON files (id ->
side_effect_class), neither of which is pack-specific code. It has no knowledge of .NET, csproj
files, or any other domain content."""

from __future__ import annotations

import json
from pathlib import Path

ANCHOR_CATEGORIES = ("project-format", "target-framework", "package-management", "incompatible-api")


def load_findings_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_template_side_effect_classes(templates_dir: Path) -> dict[str, str]:
    classes = {}
    for template_path in sorted(templates_dir.glob("*.json")):
        data = json.loads(template_path.read_text(encoding="utf-8"))
        classes[data["id"]] = data["side_effect_class"]
    return classes


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


def generate_phases(findings_document: dict, templates_dir: Path) -> tuple[list[dict], list[str]]:
    """Returns (phases, dropped_finding_ids). A finding with no remediation_tag is
    informational -- there is nothing to group it into a phase for -- and is dropped from the
    plan, but never silently: its id is returned so the caller can record it, matching the
    project's own rule that nothing gets skipped without a trace (AUDIT-1's FINDING_DISCARDED
    precedent, even though this is a different case -- informational, not invalid)."""
    findings = findings_document["findings"]
    side_effect_classes = load_template_side_effect_classes(templates_dir)
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
        tag, _component = key
        group = groups[key]
        if tag not in side_effect_classes:
            raise ValueError(f"remediation_tag {tag!r} (finding(s) {[f['id'] for f in group]}) has no matching node template in {templates_dir}")

        affected_paths = sorted({p for f in group for p in f["affected_paths"]})
        finding_ids = sorted(f["id"] for f in group)
        descriptions = "; ".join(sorted({f["description"] for f in group}))

        phases.append({
            "id": f"phase-{n}-{tag}",
            "description": f"[{tag}] {descriptions} (findings: {', '.join(finding_ids)})",
            "declared_scope": affected_paths,
            "side_effect_class": side_effect_classes[tag],
            "edits": [],
        })

    return phases, dropped


def generate_plan(findings_path: Path, templates_dir: Path, check_set: list[dict], run_id_prefix: str) -> dict:
    document = load_findings_file(findings_path)
    phases, dropped = generate_phases(document, templates_dir)

    description = (
        f"Generated {document['generated_at']} from '{document['pack']}' audit of "
        f"{document['target_repo']} (pack_content_hash {document['pack_content_hash'][:16]}...). "
        f"{len(phases)} phase(s) from {len(document['findings'])} finding(s). "
        "Every phase's edits are empty by design -- this generator only groups findings into "
        "phases (PLAN-1/PLAN-2 v1 scope, category + declared-path overlap only); literal "
        "remediation content requires either hand-authoring or an LLM implementer (Phase E)."
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
