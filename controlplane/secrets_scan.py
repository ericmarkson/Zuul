"""Pre-approval secret scan — FRD SECRET-1. Advisory-with-forced-acknowledgment, not a filter:
this module never masks or removes anything, it only surfaces findings for the operator to
acknowledge at the approval checkpoint."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from controlplane import gitops

CREDENTIAL_SHAPED_PATTERNS = (".env", "*.pfx", "*.p12", "*.pem", "*credentials*.json")

_SECRET_PATTERNS = (
    ("password_assignment", re.compile(r"password[\"']?\s*[:=]\s*[\"'][^\"']{4,}[\"']", re.IGNORECASE)),
    ("connection_string_password", re.compile(r"(?:password|pwd)\s*=\s*[^;\"'\s]{4,}", re.IGNORECASE)),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_api_key", re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"'][^\"']{8,}[\"']", re.IGNORECASE)),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
)


@dataclass(frozen=True)
class SecretFinding:
    path: str
    kind: str
    detail: str


def scan(repo: Path, baseline_sha: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    tracked = gitops.git(repo, "ls-tree", "-r", "--name-only", baseline_sha).stdout.splitlines()

    for rel_path in tracked:
        if not rel_path.strip():
            continue
        for pattern in CREDENTIAL_SHAPED_PATTERNS:
            if Path(rel_path).match(pattern):
                findings.append(SecretFinding(path=rel_path, kind="credential_shaped_path", detail=f"tracked path matches {pattern!r}"))

        abs_path = repo / rel_path
        if not abs_path.is_file():
            continue
        try:
            text = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for kind, pattern in _SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append(SecretFinding(path=rel_path, kind=kind, detail=match.group(0)[:80]))

    return findings
