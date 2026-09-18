"""Plan loading — FRD PLAN-1 (operator-authored path) and PLAN-5 (per-phase declared scope /
check set / side-effect class, frozen once loaded)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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
class PhaseSpec:
    id: str
    description: str
    declared_scope: list[str]
    side_effect_class: str
    edits: list[EditSpec]


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
