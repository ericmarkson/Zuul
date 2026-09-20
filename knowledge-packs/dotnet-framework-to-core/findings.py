"""The findings schema — FRD AUDIT-1. A finding carries, at minimum, a category, a severity,
and one or more affected paths; this pack always includes an id, description, and remediation
tag too, but AUDIT-1 only requires the first three."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PACK_NAME = "dotnet-framework-to-core"
SCHEMA_VERSION = "0.1"

SEVERITIES = ("low", "medium", "high")


@dataclass(frozen=True)
class Finding:
    id: str
    category: str
    severity: str
    affected_paths: list[str]
    description: str
    remediation_tag: str | None = None
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}, expected one of {SEVERITIES}")
        if not self.affected_paths:
            raise ValueError(f"finding {self.id} has no affected_paths (AUDIT-1 requires at least one)")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "affected_paths": self.affected_paths,
            "description": self.description,
            "remediation_tag": self.remediation_tag,
            "evidence": self.evidence,
        }


def pack_content_hash(pack_dir: Path) -> str:
    """A simple, deterministic hash of this pack's own source files, for the run-time content
    hash EXEC-6/KNOWLEDGE-4 will eventually record when a run actually loads this pack. Not
    wired into the control plane yet -- Phase C only needs the pack to be able to identify
    itself; the control plane doing the recording is a later integration point."""
    hasher = hashlib.sha256()
    for path in sorted(pack_dir.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            hasher.update(path.relative_to(pack_dir).as_posix().encode("utf-8"))
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def write_findings_file(path: Path, findings: list[Finding], target_repo: Path, pack_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": SCHEMA_VERSION,
        "pack": PACK_NAME,
        "pack_content_hash": pack_content_hash(pack_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_repo": str(target_repo),
        "findings": [f.to_dict() for f in findings],
    }
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
