"""Integration-level, hermetic tests for EXEC-7 inside Runner itself: a real crash (an
uncaught exception mid-phase), a real second-process lock collision, and a real reuse of an
already-completed run id -- not just the isolated run_lock.py/resume.py pieces."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.model_provider import BudgetedProvider, MockModelProvider, ModelResponse  # noqa: E402
from controlplane.run_lock import RunLock  # noqa: E402
from controlplane.runner import Runner  # noqa: E402


class RunnerResumeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.fixture = base / "fixture"
        self.fixture.mkdir()
        (self.fixture / "greeting.txt").write_text("hello", encoding="utf-8")
        self.scratch = base / "scratch"

        plan = {
            "schema_version": "0.1",
            "run_id_prefix": "resume-test",
            "plan_description": "test",
            "check_set": [{
                "id": "check",
                "command": [sys.executable, "-c", "pass"],
                "result_artifact": str(base / "unused.xml"),
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
        self.plan_path = base / "plan.json"
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _runner(self, run_id: str, model_provider) -> Runner:
        return Runner(
            plan_path=self.plan_path,
            fixture_template=self.fixture,
            edits_dir=Path(self._tmp.name) / "no-edits",
            scratch_root=self.scratch,
            auto_approve=True,
            model_provider=model_provider,
            run_id=run_id,
        )

    def test_a_crash_mid_phase_leaves_a_run_that_is_detected_as_incomplete_on_restart(self):
        crashing_provider = BudgetedProvider(
            inner=MockModelProvider(responses=[RuntimeError("simulated process crash")]),
            max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        first = self._runner("crash-test-1", crashing_provider)
        with self.assertRaises(RuntimeError):
            first.run()

        # the "process" died mid-phase; the lock must not still be held (the OS would have
        # released it on a real crash -- here, the try/finally in Runner.run() does the
        # equivalent as the exception unwinds)
        second_lock = RunLock(first.run_dir / "run.lock")
        second_lock.acquire()  # must not raise RunLockHeld
        second_lock.release()

        # a fresh Runner instance pointed at the SAME run id must detect the incomplete prior
        # state and refuse to auto-resume or auto-reset, rather than silently starting over
        working_provider = BudgetedProvider(
            inner=MockModelProvider(responses=[]),
            max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        second = self._runner("crash-test-1", working_provider)
        result = second.run()

        self.assertFalse(result)
        self.assertEqual(working_provider.inner.calls, [])  # never even attempted the phase again
        resume_report_path = first.run_dir / "resume_report.json"
        self.assertTrue(resume_report_path.exists())
        report = json.loads(resume_report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["last_event"]["event_type"], "PHASE_STARTED")
        self.assertIsNone(report["last_committed_phase"])

    def test_concurrent_process_is_refused_by_the_lock_not_treated_as_a_resume(self):
        provider = BudgetedProvider(
            inner=MockModelProvider(responses=[]),
            max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        runner = self._runner("concurrent-test", provider)

        # simulate a second, still-alive process already holding this run's lock
        rival = RunLock(runner.run_dir / "run.lock")
        rival.acquire()
        try:
            result = runner.run()
            self.assertFalse(result)
            # refused before ever touching the target repo -- no materialization attempted
            self.assertFalse(runner.target_repo.exists())
        finally:
            rival.release()

    def test_reusing_an_already_completed_run_id_is_refused_not_silently_rerun(self):
        response = ModelResponse(
            content=json.dumps({"edits": [{"path": "greeting.txt", "content": "hello world"}]}),
            input_tokens=5, output_tokens=5, latency_seconds=0.01,
        )
        provider = BudgetedProvider(
            inner=MockModelProvider(responses=[response]),
            max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        first = self._runner("reuse-test", provider)
        self.assertTrue(first.run())

        second = self._runner("reuse-test", provider)
        self.assertFalse(second.run())


if __name__ == "__main__":
    unittest.main()
