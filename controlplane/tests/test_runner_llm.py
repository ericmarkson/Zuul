"""Integration-level, hermetic tests for the LLM-driven phase path inside Runner itself --
EXEC-3's retry loop, INTEGRITY-8's file-only reset between attempts, and BUDGET-2's immediate
escalation on overrun. MockModelProvider only, zero network. A tiny synthetic single-file
fixture, not the .NET one, so this stays fast and has nothing to do with any specific domain."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.eventlog import EventType  # noqa: E402
from controlplane.model_provider import BudgetedProvider, MockModelProvider, ModelResponse, ToolCall  # noqa: E402
from controlplane.runner import Runner  # noqa: E402

CHECK_SCRIPT = (
    "import sys\n"
    "content = open('greeting.txt').read()\n"
    "sys.exit(0 if content.strip() == 'hello world' else 1)\n"
)


def _finalize(edits: list[dict], in_tok: int = 10, out_tok: int = 10) -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=in_tok, output_tokens=out_tok, latency_seconds=0.01,
        tool_calls=(ToolCall(id="call-1", name="finalize_edits", arguments={"edits": edits}),),
    )


def _malformed(content: str = "not calling any tool") -> ModelResponse:
    return ModelResponse(content=content, input_tokens=10, output_tokens=10, latency_seconds=0.01)


class RunnerLlmTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.fixture = base / "fixture"
        self.fixture.mkdir()
        self.scratch = base / "scratch"

    def tearDown(self):
        self._tmp.cleanup()

    def _write_plan(self, initial_content: str) -> Path:
        (self.fixture / "greeting.txt").write_text(initial_content, encoding="utf-8")
        plan = {
            "schema_version": "0.1",
            "run_id_prefix": "llm-test",
            "plan_description": "test",
            "check_set": [{
                "id": "check",
                "command": [sys.executable, "-c", CHECK_SCRIPT],
                "result_artifact": str(Path(self._tmp.name) / "unused.xml"),
                "result_format": "junit",
            }],
            "phases": [{
                "id": "phase-1",
                "description": "set greeting.txt to 'hello world'",
                "declared_scope": ["greeting.txt"],
                "side_effect_class": "file-only",
                "edits": [],
            }],
        }
        plan_path = Path(self._tmp.name) / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return plan_path

    def _runner(self, plan_path: Path, model_provider) -> Runner:
        return Runner(
            plan_path=plan_path,
            fixture_template=self.fixture,
            edits_dir=Path(self._tmp.name) / "no-edits",
            scratch_root=self.scratch,
            auto_approve=True,
            model_provider=model_provider,
            retry_budget=2,
        )

    def test_llm_phase_succeeds_on_first_attempt(self):
        plan_path = self._write_plan("hello")
        mock = MockModelProvider(responses=[_finalize([{"path": "greeting.txt", "content": "hello world"}])])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertTrue(runner.run())
        events = runner.event_log.read_all()
        committed = [e for e in events if e["event_type"] == "PHASE_COMMITTED"]
        self.assertEqual(len(committed), 1)
        self.assertEqual(committed[0]["attempts"], 1)

    def test_malformed_response_retries_then_succeeds(self):
        plan_path = self._write_plan("hello")
        mock = MockModelProvider(responses=[
            _malformed(),
            _finalize([{"path": "greeting.txt", "content": "hello world"}]),
        ])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertTrue(runner.run())
        events = runner.event_log.read_all()
        committed = [e for e in events if e["event_type"] == "PHASE_COMMITTED"]
        self.assertEqual(committed[0]["attempts"], 2)

    def test_persistent_check_regression_exhausts_retry_budget_and_escalates(self):
        """Baseline already passes ('hello world'); every proposed edit breaks it. After
        retry_budget + 1 attempts, this must escalate as validation-loop, not loop forever."""
        plan_path = self._write_plan("hello world")
        mock = MockModelProvider(responses=[
            _finalize([{"path": "greeting.txt", "content": "broken"}]),
            _finalize([{"path": "greeting.txt", "content": "still broken"}]),
            _finalize([{"path": "greeting.txt", "content": "still broken again"}]),
        ])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertFalse(runner.run())
        events = runner.event_log.read_all()
        escalated = [e for e in events if e["event_type"] == "ESCALATED"]
        self.assertEqual(len(escalated), 1)
        self.assertEqual(escalated[0]["category"], "validation-loop")
        self.assertEqual(len(mock.tool_calls_log), 3)  # retry_budget=2 -> 3 total attempts, then stop

    def test_phase_reset_between_attempts_does_not_leak_the_bad_edit(self):
        """INTEGRITY-8: a file-only phase resets to its pre-attempt baseline before retrying --
        the failed attempt's content must not still be present once a later attempt succeeds."""
        plan_path = self._write_plan("hello world")
        mock = MockModelProvider(responses=[
            _finalize([{"path": "greeting.txt", "content": "broken"}]),
            _finalize([{"path": "greeting.txt", "content": "hello world"}]),
        ])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertTrue(runner.run())
        final_content = (runner.target_repo / "greeting.txt").read_text(encoding="utf-8")
        self.assertEqual(final_content, "hello world")

    def test_budget_exceeded_escalates_immediately_without_retry(self):
        plan_path = self._write_plan("hello")
        mock = MockModelProvider(responses=[_finalize([{"path": "greeting.txt", "content": "hello world"}])])
        # zero phase budget -> the pre-call guard (capped_max_output <= 0) must refuse before
        # ever reaching the model, not just detect an overage after a call returns.
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=0, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertFalse(runner.run())
        events = runner.event_log.read_all()
        self.assertTrue(any(e["event_type"] == "BUDGET_EXCEEDED" for e in events))
        escalated = [e for e in events if e["event_type"] == "ESCALATED"]
        self.assertEqual(escalated[0]["category"], "budget-exceeded")
        self.assertEqual(mock.tool_calls_log, [])  # the wrapper must refuse before ever calling the model

    def test_budget_overage_detected_after_a_call_that_used_more_than_requested(self):
        """The complementary case: a small-but-nonzero phase budget permits a capped call, and
        the wrapper still catches the overage once real usage comes back, rather than trusting
        the cap was honored."""
        plan_path = self._write_plan("hello")
        mock = MockModelProvider(responses=[_finalize([{"path": "greeting.txt", "content": "hello world"}])])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertFalse(runner.run())
        self.assertEqual(len(mock.tool_calls_log), 1)  # the call did happen this time
        events = runner.event_log.read_all()
        escalated = [e for e in events if e["event_type"] == "ESCALATED"]
        self.assertEqual(escalated[0]["category"], "budget-exceeded")


if __name__ == "__main__":
    unittest.main()
