"""Plan loading — FRD PLAN-1 (operator-authored path) and PLAN-5 (per-phase declared scope /
check set / side-effect class, frozen once loaded)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CheckSpec:
    id: str
    command: list[str]
    result_artifact: str
    result_format: str


@dataclass(frozen=True)
class EditSpec:
    path: str
    content_file: str


@dataclass(frozen=True)
class CheckFixture:
    """A file a phase's own check needs to exist to run (most commonly a test source file) --
    written and committed by the runner *before* the phase's attempt loop begins, and
    deliberately never part of `declared_scope`, so INTEGRITY-3's unmodified scope diff protects
    it from the implementer the same way it protects everything else outside scope."""
    path: str
    content: str


@dataclass(frozen=True)
class PhaseSpec:
    id: str
    description: str
    declared_scope: list[str]
    side_effect_class: str
    edits: list[EditSpec]
    # PLAN-5: each phase declares its own check set. None means "use the plan's default
    # check_set" -- most hand-authored phases never need more than that; a generated phase
    # whose node template knows what success looks like (e.g. "this file should now exist")
    # can add its own on top, per plangen.py.
    checks: list[CheckSpec] | None = None
    check_fixtures: list[CheckFixture] = field(default_factory=list)


@dataclass(frozen=True)
class Plan:
    schema_version: str
    run_id_prefix: str
    plan_description: str
    check_set: list[CheckSpec]
    phases: list[PhaseSpec]
    content_hash: str
    source_path: Path


def load_plan(path: Path) -> Plan:
    raw = path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    data = json.loads(raw)

    check_set = [
        CheckSpec(
            id=c["id"],
            command=c["command"],
            result_artifact=c["result_artifact"],
            result_format=c["result_format"],
        )
        for c in data["check_set"]
    ]
    phases = [
        PhaseSpec(
            id=p["id"],
            description=p["description"],
            declared_scope=list(p["declared_scope"]),
            side_effect_class=p["side_effect_class"],
            edits=[EditSpec(path=e["path"], content_file=e["content_file"]) for e in p["edits"]],
            checks=(
                [CheckSpec(id=c["id"], command=c["command"], result_artifact=c["result_artifact"], result_format=c["result_format"]) for c in p["checks"]]
                if p.get("checks") is not None else None
            ),
            check_fixtures=[CheckFixture(path=f["path"], content=f["content"]) for f in p.get("check_fixtures", [])],
        )
        for p in data["phases"]
    ]

    return Plan(
        schema_version=data["schema_version"],
        run_id_prefix=data["run_id_prefix"],
        plan_description=data["plan_description"],
        check_set=check_set,
        phases=phases,
        content_hash=content_hash,
        source_path=path,
    )
