"""CLI entrypoint. Usage:

    python -m controlplane.cli run --plan plans/sample-plan.json
    python -m controlplane.cli generate-plan --findings <findings.json> --templates <dir> \\
        --check-command dotnet build Foo.sln --run-id-prefix my-run --out plans/generated.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from controlplane import plangen
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

    gen_parser = subparsers.add_parser("generate-plan", help="generate a plan.json from a findings file (PLAN-1 path a)")
    gen_parser.add_argument("--findings", type=Path, required=True)
    gen_parser.add_argument("--templates", type=Path, required=True)
    gen_parser.add_argument("--check-id", default="build")
    gen_parser.add_argument("--check-command", nargs="+", required=True)
    gen_parser.add_argument("--run-id-prefix", required=True)
    gen_parser.add_argument("--out", type=Path, required=True)

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

    if args.command == "generate-plan":
        check_set = [{
            "id": args.check_id,
            "command": args.check_command,
            "result_artifact": "{run_dir}/results/{phase_id}/unused.xml",
            "result_format": "junit",
        }]
        plan = plangen.generate_plan(
            findings_path=args.findings,
            templates_dir=args.templates,
            check_set=check_set,
            run_id_prefix=args.run_id_prefix,
        )
        plangen.write_plan_file(args.out, plan)
        dropped = plan["_generated_from"]["dropped_informational_findings"]
        print(f"{len(plan['phases'])} phase(s) generated from {args.findings}")
        if dropped:
            print(f"{len(dropped)} informational finding(s) excluded (no remediation_tag): {dropped}")
        print(f"written to {args.out}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
