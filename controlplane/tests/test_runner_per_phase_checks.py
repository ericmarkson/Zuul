"""FRD PLAN-5: a phase may declare its own check set. This is the gap Phase F's first real run
surfaced -- a phase-specific check (e.g. "did this phase create the file it promised") has no
baseline counterpart, so any failure there must count directly, not be tolerated as a
pre-existing delta. Hermetic, tiny synthetic fixture, no LLM involved."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.runner import Runner  # noqa: E402


class PerPhaseCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.fixture = base / "fixture"
        self.fixture.mkdir()
        (self.fixture / "greeting.txt").write_text("hello", encoding="utf-8")
        self.edits_dir = base / "edits"
        self.edits_dir.mkdir()
        self.scratch = base / "scratch"
        self.base = base

    def tearDown(self):
        self._tmp.cleanup()

    def _write_plan(self, phase_checks) -> Path:
        plan = {
            "schema_version": "0.1",
            "run_id_prefix": "phase-checks-test",
            "plan_description": "test",
            "check_set": [{
                "id": "always-pass",
                "command": [sys.executable, "-c", "pass"],
                "result_artifact": str(self.base / "unused.xml"),
                "result_format": "junit",
            }],
            "phases": [{
                "id": "phase-1",
                "description": "write output.txt",
                "declared_scope": ["greeting.txt", "output.txt"],
                "side_effect_class": "file-only",
                "edits": [{"path": "greeting.txt", "content_file": "greeting-edit.txt"}],
                "checks": phase_checks,
            }],
        }
        (self.edits_dir / "greeting-edit.txt").write_text("hello world", encoding="utf-8")
        plan_path = self.base / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return plan_path

    def _runner(self, plan_path: Path) -> Runner:
        return Runner(plan_path=plan_path, fixture_template=self.fixture, edits_dir=self.edits_dir, scratch_root=self.scratch, auto_approve=True)

    def test_phase_with_no_declared_checks_uses_the_plan_default(self):
        plan_path = self._write_plan(None)
        runner = self._runner(plan_path)
        self.assertTrue(runner.run())
        events = runner.event_log.read_all()
        check_results = [e for e in events if e["event_type"] == "CHECK_RESULT" and e["phase_id"] == "phase-1"]
        self.assertEqual([c["check_id"] for c in check_results], ["always-pass"])

    def test_phase_specific_check_that_passes_does_not_block_success(self):
        expects_output_check = {
            "id": "output-exists",
            "command": [sys.executable, "-c", "import pathlib, sys; sys.exit(0 if pathlib.Path('output.txt').is_file() else 1)"],
            "result_artifact": str(self.base / "unused2.xml"),
            "result_format": "junit",
        }
        plan_path = self._write_plan([expects_output_check])
        (self.edits_dir / "greeting-edit.txt").write_text("hello world", encoding="utf-8")
        # this phase's edits list only writes greeting.txt; the check expects output.txt too --
        # simulate a template whose remediation the "implementer" actually satisfies by also
        # writing the expected file via a second literal edit
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["phases"][0]["edits"].append({"path": "output.txt", "content_file": "output-edit.txt"})
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        (self.edits_dir / "output-edit.txt").write_text("produced", encoding="utf-8")

        runner = self._runner(plan_path)
        self.assertTrue(runner.run())

    def test_phase_specific_check_with_no_baseline_counterpart_that_fails_escalates(self):
        """The exact gap from Phase F's first run: a phase-specific check has nothing to
        compare against at baseline, so a failure here must not be silently tolerated as a
        'pre-existing' condition -- it must escalate."""
        expects_output_check = {
            "id": "output-exists",
            "command": [sys.executable, "-c", "import pathlib, sys; sys.exit(0 if pathlib.Path('output.txt').is_file() else 1)"],
            "result_artifact": str(self.base / "unused3.xml"),
            "result_format": "junit",
        }
        plan_path = self._write_plan([expects_output_check])
        # deliberately do NOT create output.txt -- the phase only edits greeting.txt, exactly
        # like the real modernize-config-file failure: it did something, just not what the
        # check expects

        runner = self._runner(plan_path)
        self.assertFalse(runner.run())
        events = runner.event_log.read_all()
        escalated = [e for e in events if e["event_type"] == "ESCALATED"]
        self.assertEqual(len(escalated), 1)
        self.assertEqual(escalated[0]["category"], "validation-loop")


if __name__ == "__main__":
    unittest.main()
