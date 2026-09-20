"""Regression coverage for a real bug found live during Phase F's third run, 2026-09-20: a
model-authored check script containing an ordinary brace not meant as a plan placeholder (e.g.
`tag.rsplit('}', 1)`, for stripping an XML namespace) crashed `_run_check_set` because it called
`str.format()` on the whole command, which interprets every brace in the string. Hermetic --
no real model involved, just a script literal reproducing the exact shape that broke."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.runner import Runner  # noqa: E402

# The exact failure shape: a lone '}' inside an ordinary Python string literal, not a
# {run_dir}/{phase_id}/{result_artifact} placeholder. str.format() raises ValueError on this;
# literal substring replacement must not.
SCRIPT_WITH_STRAY_BRACE = (
    "import sys\n"
    "tag = 'ns}Local'\n"
    "sys.exit(0 if tag.rsplit('}', 1)[-1] == 'Local' else 1)\n"
)


class SubstitutePlaceholdersTests(unittest.TestCase):
    def test_known_placeholders_are_substituted(self):
        result = Runner._substitute_placeholders("{run_dir}/{phase_id}/x", run_dir="R", phase_id="P")
        self.assertEqual(result, "R/P/x")

    def test_unrelated_braces_are_left_untouched_rather_than_raising(self):
        result = Runner._substitute_placeholders(SCRIPT_WITH_STRAY_BRACE, run_dir="R", phase_id="P", result_artifact="A")
        self.assertEqual(result, SCRIPT_WITH_STRAY_BRACE)  # nothing in it matches a known token

    def test_mixed_placeholder_and_stray_brace_both_resolve_correctly(self):
        text = "{phase_id}: tag.rsplit('}', 1)"
        result = Runner._substitute_placeholders(text, run_dir="R", phase_id="P", result_artifact="A")
        self.assertEqual(result, "P: tag.rsplit('}', 1)")


class RunnerCheckWithStrayBraceTests(unittest.TestCase):
    """End-to-end: a phase whose own check script contains a stray brace must not crash the
    run -- this is exactly the shape a model-authored check (2026-09-20 pivot) can produce."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.fixture = base / "fixture"
        self.fixture.mkdir()
        (self.fixture / "greeting.txt").write_text("hello world", encoding="utf-8")
        self.scratch = base / "scratch"

        plan = {
            "schema_version": "0.1",
            "run_id_prefix": "brace-test",
            "plan_description": "test",
            "check_set": [{
                "id": "check",
                "command": [sys.executable, "-c", "pass"],
                "result_artifact": str(base / "unused.xml"),
                "result_format": "junit",
            }],
            "phases": [{
                "id": "phase-1",
                "description": "no-op phase whose own check script has a stray brace",
                "declared_scope": ["greeting.txt"],
                "side_effect_class": "file-only",
                "edits": [{"path": "greeting.txt", "content_file": "greeting.txt"}],
                "checks": [{
                    "id": "stray-brace-check",
                    "command": [sys.executable, "-c", SCRIPT_WITH_STRAY_BRACE],
                    "result_artifact": "{run_dir}/results/{phase_id}/unused.xml",
                    "result_format": "junit",
                }],
            }],
        }
        self.plan_path = base / "plan.json"
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")

        self.edits_dir = base / "edits"
        self.edits_dir.mkdir()
        (self.edits_dir / "greeting.txt").write_text("hello world", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_phase_with_stray_brace_in_its_own_check_script_runs_to_completion(self):
        runner = Runner(
            plan_path=self.plan_path,
            fixture_template=self.fixture,
            edits_dir=self.edits_dir,
            scratch_root=self.scratch,
            auto_approve=True,
        )
        self.assertTrue(runner.run())
        events = runner.event_log.read_all()
        committed = [e for e in events if e["event_type"] == "PHASE_COMMITTED"]
        self.assertEqual(len(committed), 1)


if __name__ == "__main__":
    unittest.main()
