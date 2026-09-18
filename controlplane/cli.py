"""CLI entrypoint for Phase A. Usage:

    python -m controlplane.cli run --plan plans/sample-plan.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from controlplane.runner import Runner

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="controlplane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="execute a plan (Phase A vertical slice)")
    run_parser.add_argument("--plan", type=Path, default=REPO_ROOT / "plans" / "sample-plan.json")
    run_parser.add_argument("--fixture", type=Path, default=REPO_ROOT / "fixtures" / "sample-dotnet-app")
    run_parser.add_argument("--edits", type=Path, default=REPO_ROOT / "fixtures" / "sample-dotnet-app-edits")
    run_parser.add_argument("--scratch", type=Path, default=REPO_ROOT / ".scratch")
    run_parser.add_argument("--yes", action="store_true", help="auto-approve every prompt (non-interactive demo/CI use only)")

    args = parser.parse_args(argv)

    if args.command == "run":
        runner = Runner(
            plan_path=args.plan,
            fixture_template=args.fixture,
            edits_dir=args.edits,
            scratch_root=args.scratch,
            auto_approve=args.yes,
        )
        ok = runner.run()
        print(f"\nrun_id={runner.run_id}")
        print(f"event_log={runner.event_log.path}")
        print(f"diagnostic_log={runner.diag_log.path}")
        return 0 if ok else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
