"""Hermetic -- no subprocess, no model. `present_gate` is what the human operator actually reads
before `APPROVAL-1`'s single gate; a real, separate transparency bug was found live, 2026-09-20,
alongside the check_fixtures work: it always displayed the *plan's* default check set, never a
phase's own PLAN-5 override -- the exact same class of bug already fixed for the implementer's
own prompt, except this one hid the real check from the human operator, not the model."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.checks import CheckResult  # noqa: E402
from controlplane.gate import present_gate  # noqa: E402
from controlplane.plan import CheckFixture, CheckSpec, Plan, PhaseSpec  # noqa: E402


def _plan(phases: list[PhaseSpec]) -> Plan:
    return Plan(
        schema_version="0.1", run_id_prefix="test", plan_description="test plan",
        check_set=[CheckSpec(id="default-check", command=["true"], result_artifact="x", result_format="junit")],
        phases=phases, content_hash="deadbeef", source_path=Path("plan.json"),
    )


class PresentGateTests(unittest.TestCase):
    def test_a_phase_specific_check_set_is_shown_not_the_plan_default(self):
        phase = PhaseSpec(
            id="phase-1", description="d", declared_scope=["a.cs"], side_effect_class="file-only", edits=[],
            checks=[CheckSpec(id="phase-specific-check", command=["true"], result_artifact="x", result_format="junit")],
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            present_gate(_plan([phase]), "abc123", [])
        output = buf.getvalue()
        self.assertIn("phase-specific-check", output)
        self.assertNotIn("default-check", output)

    def test_a_phase_with_no_check_override_shows_the_plan_default(self):
        phase = PhaseSpec(id="phase-1", description="d", declared_scope=["a.cs"], side_effect_class="file-only", edits=[], checks=None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            present_gate(_plan([phase]), "abc123", [])
        self.assertIn("default-check", buf.getvalue())

    def test_check_fixtures_are_displayed_when_present(self):
        phase = PhaseSpec(
            id="phase-1", description="d", declared_scope=["a.cs"], side_effect_class="file-only", edits=[],
            check_fixtures=[CheckFixture(path="tests/Foo.Tests.cs", content="// test")],
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            present_gate(_plan([phase]), "abc123", [])
        self.assertIn("tests/Foo.Tests.cs", buf.getvalue())

    def test_no_fixture_line_is_printed_when_there_are_none(self):
        phase = PhaseSpec(id="phase-1", description="d", declared_scope=["a.cs"], side_effect_class="file-only", edits=[])
        buf = io.StringIO()
        with redirect_stdout(buf):
            present_gate(_plan([phase]), "abc123", [])
        self.assertNotIn("check fixtures", buf.getvalue())

    def test_baseline_results_are_shown(self):
        phase = PhaseSpec(id="phase-1", description="d", declared_scope=["a.cs"], side_effect_class="file-only", edits=[])
        result = CheckResult(check_id="default-check", exit_code=1, test_outcomes={"t1": "Failed"})
        buf = io.StringIO()
        with redirect_stdout(buf):
            present_gate(_plan([phase]), "abc123", [result])
        self.assertIn("1 pre-existing failure(s)", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
