"""CLI entrypoint. Usage:

    python -m controlplane.cli run --plan plans/sample-plan.json
    python -m controlplane.cli generate-plan --findings <findings.json> \\
        --check-command dotnet build Foo.sln --run-id-prefix my-run --out plans/generated.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from controlplane import plangen
from controlplane.runner import Runner

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Minimal, dependency-free .env loader -- DISCLOSE-1/SECRET-1 territory: this never logs
    or prints what it loads, and existing environment variables always win over the file."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="controlplane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="execute a plan (Phase A vertical slice)")
    run_parser.add_argument("--plan", type=Path, default=REPO_ROOT / "plans" / "sample-plan.json")
    run_parser.add_argument("--fixture", type=Path, default=REPO_ROOT / "fixtures" / "sample-dotnet-app")
    run_parser.add_argument("--edits", type=Path, default=REPO_ROOT / "fixtures" / "sample-dotnet-app-edits")
    run_parser.add_argument("--scratch", type=Path, default=REPO_ROOT / ".scratch")
    run_parser.add_argument("--yes", action="store_true", help="auto-approve every prompt (non-interactive demo/CI use only)")
    run_parser.add_argument("--model-provider", choices=["none", "openai"], default="none", help="Phase E: use a real model for phases with no pre-authored edits")
    run_parser.add_argument("--model", default="gpt-5.6-sol")
    run_parser.add_argument("--reasoning-effort", default="low")
    run_parser.add_argument("--retry-budget", type=int, default=2, help="EXEC-3: bounded retries per phase")
    run_parser.add_argument("--llm-max-output-tokens", type=int, default=8000)
    run_parser.add_argument("--llm-max-tool-rounds", type=int, default=6, help="bounded multi-step tool-calling loop for the LLM implementer")
    run_parser.add_argument("--max-tokens-per-phase", type=int, default=20000, help="BUDGET-1")
    run_parser.add_argument("--max-tokens-per-run", type=int, default=100000, help="BUDGET-1")
    run_parser.add_argument("--wall-clock-per-phase-seconds", type=float, default=180, help="BUDGET-1")
    run_parser.add_argument("--wall-clock-per-run-seconds", type=float, default=1800, help="BUDGET-1")
    run_parser.add_argument("--run-id", default=None, help="EXEC-7: reuse a run id to make this run addressable/resumable across process restarts. Omit for a fresh, always-new run.")

    gen_parser = subparsers.add_parser("generate-plan", help="generate a plan.json from a findings file via one LLM call per finding-group (PLAN-1 path a)")
    gen_parser.add_argument("--findings", type=Path, required=True)
    gen_parser.add_argument("--check-id", default="build")
    gen_parser.add_argument("--check-command", nargs="+", required=True)
    gen_parser.add_argument("--run-id-prefix", required=True)
    gen_parser.add_argument("--out", type=Path, required=True)
    gen_parser.add_argument("--model", default="gpt-5.6-sol")
    gen_parser.add_argument("--reasoning-effort", default="low")
    gen_parser.add_argument("--llm-max-output-tokens", type=int, default=4000)
    gen_parser.add_argument("--llm-max-tool-rounds", type=int, default=8, help="bounded research loop per finding-group (grep_repo/list_directory/read_file, then finalize_proposal)")
    gen_parser.add_argument("--max-tokens-total", type=int, default=50000, help="BUDGET-1, applied to this whole generation batch")
    gen_parser.add_argument("--wall-clock-seconds", type=float, default=600, help="BUDGET-1, applied to this whole generation batch")

    args = parser.parse_args(argv)

    if args.command == "run":
        model_provider = None
        if args.model_provider == "openai":
            _load_dotenv(REPO_ROOT / ".env")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("error: OPENAI_API_KEY not set (checked .env and the environment)", file=sys.stderr)
                return 1
            from controlplane.model_provider import BudgetedProvider, OpenAIProvider

            model_provider = BudgetedProvider(
                inner=OpenAIProvider(api_key=api_key, model=args.model, reasoning_effort=args.reasoning_effort),
                max_tokens_per_phase=args.max_tokens_per_phase,
                max_tokens_per_run=args.max_tokens_per_run,
                wall_clock_limit_per_phase_seconds=args.wall_clock_per_phase_seconds,
                wall_clock_limit_per_run_seconds=args.wall_clock_per_run_seconds,
            )

        runner = Runner(
            plan_path=args.plan,
            fixture_template=args.fixture,
            edits_dir=args.edits,
            scratch_root=args.scratch,
            auto_approve=args.yes,
            model_provider=model_provider,
            retry_budget=args.retry_budget,
            llm_max_output_tokens=args.llm_max_output_tokens,
            llm_max_tool_rounds=args.llm_max_tool_rounds,
            run_id=args.run_id,
        )
        ok = runner.run()
        print(f"\nrun_id={runner.run_id}")
        print(f"event_log={runner.event_log.path}")
        print(f"diagnostic_log={runner.diag_log.path}")
        if model_provider is not None:
            from controlplane.model_provider import estimate_cost_usd

            cost = estimate_cost_usd(model_provider.run_input_tokens, model_provider.run_output_tokens)
            print(f"model tokens: {model_provider.run_input_tokens} in / {model_provider.run_output_tokens} out (~${cost:.4f})")
        return 0 if ok else 1

    if args.command == "generate-plan":
        _load_dotenv(REPO_ROOT / ".env")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("error: OPENAI_API_KEY not set (checked .env and the environment)", file=sys.stderr)
            return 1
        from controlplane.model_provider import BudgetedProvider, OpenAIProvider

        model_provider = BudgetedProvider(
            inner=OpenAIProvider(api_key=api_key, model=args.model, reasoning_effort=args.reasoning_effort),
            max_tokens_per_phase=args.max_tokens_total,
            max_tokens_per_run=args.max_tokens_total,
            wall_clock_limit_per_phase_seconds=args.wall_clock_seconds,
            wall_clock_limit_per_run_seconds=args.wall_clock_seconds,
        )

        check_set = [{
            "id": args.check_id,
            "command": args.check_command,
            "result_artifact": "{run_dir}/results/{phase_id}/unused.xml",
            "result_format": "junit",
        }]
        plan = plangen.generate_plan(
            findings_path=args.findings,
            model_provider=model_provider,
            check_set=check_set,
            run_id_prefix=args.run_id_prefix,
            max_output_tokens=args.llm_max_output_tokens,
            max_tool_rounds=args.llm_max_tool_rounds,
        )
        plangen.write_plan_file(args.out, plan)

        from controlplane.model_provider import estimate_cost_usd

        cost = estimate_cost_usd(model_provider.run_input_tokens, model_provider.run_output_tokens)
        print(f"model tokens: {model_provider.run_input_tokens} in / {model_provider.run_output_tokens} out (~${cost:.4f})")
        dropped = plan["_generated_from"]["dropped_informational_findings"]
        print(f"{len(plan['phases'])} phase(s) generated from {args.findings}")
        if dropped:
            print(f"{len(dropped)} informational finding(s) excluded (no remediation_tag): {dropped}")
        print(f"written to {args.out}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
