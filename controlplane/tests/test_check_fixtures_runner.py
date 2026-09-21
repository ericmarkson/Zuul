"""Integration-level, hermetic tests for a phase's check_fixtures inside Runner itself -- the
2026-09-20 fix for a check that could be satisfied by a hollow stub (a text-based check greping
for a class name can't tell a real implementation from an empty shell with the right name; a
behavioral check that compiles and runs a real test file can't be fooled the same way). Proves
three things a mock model provider can't demonstrate on its own: the fixture exists before the
implementer's first attempt (so it can `read_file` it, same as any other file), it never appears
in the phase's declared_scope, and INTEGRITY-3's unmodified scope-diff mechanism -- not any new
code -- is what stops an implementer attempt from tampering with it. The check_set itself is a
trivial always-pass command throughout, deliberately decoupled from the fixture's own content, so
these tests isolate the fixture mechanics rather than any particular check's pass/fail logic.
MockModelProvider only, zero network."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.model_provider import BudgetedProvider, MockModelProvider, ModelResponse, ToolCall  # noqa: E402
from controlplane.runner import Runner  # noqa: E402


def _finalize(edits: list[dict], call_id: str = "call-1") -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name="finalize_edits", arguments={"edits": edits}),),
    )


def _tool_call(name: str, arguments: dict, call_id: str = "call-1") -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
    )


class CheckFixtureRunnerTests(unittest.TestCase):
    CHECK_SCRIPT = (
        "import sys\n"
        "content = open('greeting.txt').read()\n"
        "sys.exit(0 if content.strip() == 'hello world' else 1)\n"
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.fixture = base / "fixture"
        self.fixture.mkdir()
        (self.fixture / "greeting.txt").write_text("hello", encoding="utf-8")
        self.scratch = base / "scratch"

    def tearDown(self):
        self._tmp.cleanup()

    def _write_plan(self, check_fixtures: list[dict]) -> Path:
        plan = {
            "schema_version": "0.1",
            "run_id_prefix": "fixture-test",
            "plan_description": "test",
            "check_set": [{
                "id": "greeting-check",
                "command": [sys.executable, "-c", self.CHECK_SCRIPT],
                "result_artifact": str(Path(self._tmp.name) / "unused.xml"),
                "result_format": "junit",
            }],
            "phases": [{
                "id": "phase-1",
                "description": "set greeting.txt to 'hello world'",
                "declared_scope": ["greeting.txt"],
                "side_effect_class": "file-only",
                "edits": [],
                "check_fixtures": check_fixtures,
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

    def test_fixture_is_visible_to_the_implementer_via_read_file_before_it_finalizes(self):
        plan_path = self._write_plan([{"path": "tests/FixtureCheck.cs", "content": "// a real behavioral test"}])
        mock = MockModelProvider(responses=[
            _tool_call("read_file", {"path": "tests/FixtureCheck.cs"}),
            _finalize([{"path": "greeting.txt", "content": "hello world"}]),
        ])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertTrue(runner.run())
        tool_results = [m["content"] for m in mock.tool_calls_log[1] if m.get("role") == "tool"]
        self.assertEqual(tool_results, ["// a real behavioral test"])

    def test_fixture_never_appears_as_a_scope_violation_when_untouched(self):
        """The fixture is committed before pre_sha, so it must not show up as a "changed" path
        for a phase that never touches it -- proving it is invisible to the retry-diff mechanism,
        not merely absent from declared_scope on paper."""
        plan_path = self._write_plan([{"path": "tests/FixtureCheck.cs", "content": "// a real behavioral test"}])
        mock = MockModelProvider(responses=[_finalize([{"path": "greeting.txt", "content": "hello world"}])])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertTrue(runner.run())
        events = runner.event_log.read_all()
        scope_violations = [e for e in events if e["event_type"] == "SCOPE_VIOLATION_DETECTED"]
        self.assertEqual(scope_violations, [])
        self.assertTrue((runner.target_repo / "tests/FixtureCheck.cs").is_file())

    def test_implementer_overwriting_the_fixture_is_caught_as_a_scope_violation(self):
        """If an implementer attempt does touch the frozen fixture anyway, INTEGRITY-3's
        unmodified post-commit scope diff must catch it -- no new enforcement code, the fixture
        is protected purely by never being in declared_scope."""
        plan_path = self._write_plan([{"path": "tests/FixtureCheck.cs", "content": "// a real behavioral test"}])
        mock = MockModelProvider(responses=[_finalize([
            {"path": "greeting.txt", "content": "hello world"},
            {"path": "tests/FixtureCheck.cs", "content": "tampered!"},
        ])])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertFalse(runner.run())
        events = runner.event_log.read_all()
        escalated = [e for e in events if e["event_type"] == "ESCALATED"]
        self.assertEqual(len(escalated), 1)
        self.assertEqual(escalated[0]["category"], "scope-conflict")

    def test_fixture_survives_the_integrity8_reset_between_retry_attempts(self):
        """A failed attempt resets the target repo to pre_sha (INTEGRITY-8) -- the fixture must
        still be present after that reset, proving it was committed as part of the phase's
        starting state, not as part of a discardable attempt. attempt 1 deliberately fails the
        check (wrong greeting content), forcing a real reset --hard to pre_sha before attempt 2.
        Baseline must already pass (unlike setUp's default "hello"), or QA-5's delta evaluation
        can't distinguish attempt 1's failure from an identical pre-existing one."""
        (self.fixture / "greeting.txt").write_text("hello world", encoding="utf-8")
        plan_path = self._write_plan([{"path": "tests/FixtureCheck.cs", "content": "// a real behavioral test"}])
        mock = MockModelProvider(responses=[
            _finalize([{"path": "greeting.txt", "content": "wrong"}]),
            _finalize([{"path": "greeting.txt", "content": "hello world"}]),
        ])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertTrue(runner.run())
        events = runner.event_log.read_all()
        committed = [e for e in events if e["event_type"] == "PHASE_COMMITTED"]
        self.assertEqual(committed[0]["attempts"], 2)  # confirms the reset-and-retry path actually ran
        self.assertEqual((runner.target_repo / "tests/FixtureCheck.cs").read_text(encoding="utf-8"), "// a real behavioral test")

    def test_a_phase_with_no_check_fixtures_behaves_exactly_as_before(self):
        plan_path = self._write_plan([])
        mock = MockModelProvider(responses=[_finalize([{"path": "greeting.txt", "content": "hello world"}])])
        budgeted = BudgetedProvider(inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000, wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60)
        runner = self._runner(plan_path, budgeted)

        self.assertTrue(runner.run())
        events = runner.event_log.read_all()
        committed = [e for e in events if e["event_type"] == "PHASE_COMMITTED"]
        self.assertEqual(len(committed), 1)


if __name__ == "__main__":
    unittest.main()
