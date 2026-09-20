"""Knowledge pack CLI -- FRD KNOWLEDGE-1's v1 decision: a local, versioned directory plus a
CLI, not an MCP server. Invoked directly as a script, not as a Python module (the pack's
directory name has hyphens, which is deliberate -- it should never be importable from
controlplane/, reinforcing that the two are separate, swappable units).

Usage:
    python knowledge-packs/dotnet-framework-to-core/cli.py audit --repo <path> --out <file>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PACK_DIR))

import analyzer  # noqa: E402
from findings import write_findings_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dotnet-framework-to-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="scan a .NET repo and emit an AUDIT-1 findings file")
    audit_parser.add_argument("--repo", type=Path, required=True, help="path to the target repo to scan")
    audit_parser.add_argument("--out", type=Path, required=True, help="path to write the findings JSON to")

    args = parser.parse_args(argv)

    if args.command == "audit":
        repo_root = args.repo.resolve()
        if not repo_root.is_dir():
            print(f"error: --repo {repo_root} is not a directory", file=sys.stderr)
            return 1

        findings = analyzer.analyze_repo(repo_root)
        write_findings_file(args.out, findings, repo_root, PACK_DIR)

        by_severity = {"high": 0, "medium": 0, "low": 0}
        for f in findings:
            by_severity[f.severity] += 1

        print(f"scanned {repo_root}")
        print(f"{len(findings)} finding(s): {by_severity['high']} high, {by_severity['medium']} medium, {by_severity['low']} low")
        print(f"written to {args.out}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
