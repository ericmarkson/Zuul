"""FRD QA-2 / acceptance criterion 6: a phase whose check exits non-zero is failed by the
control plane on exit code, never on what the check's own output claims. Hermetic per TEST-1 —
no network, no subprocess beyond a local Python stub we write ourselves."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.checks import is_regression, run_check  # noqa: E402


class DeterministicVerdictTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_lying_stdout_with_no_artifact_still_fails(self):
        liar = self.tmp_path / "liar.py"
        liar.write_text("import sys\nprint('SUCCESS')\nsys.exit(1)\n", encoding="utf-8")

        result = run_check(
            cwd=self.tmp_path,
            check_id="liar",
            command=[sys.executable, str(liar)],
            result_artifact=self.tmp_path / "no-artifact-produced.xml",
            result_format="junit",
        )

        self.assertEqual(result.exit_code, 1)
        self.assertTrue(result.failed_tests, "a non-zero exit with no artifact must still read as a failure")

    def test_lying_artifact_does_not_override_nonzero_exit_code(self):
        """The sharpest case: the check's own machine-readable output claims every test passed,
        but the process that produced it exited non-zero. Exit code wins — QA-2's whole point."""
        artifact = self.tmp_path / "results.xml"
        liar = self.tmp_path / "liar_with_artifact.py"
        liar.write_text(
            "import sys\n"
            "with open(sys.argv[1], 'w') as f:\n"
            "    f.write('<testsuite><testcase name=\"t\" classname=\"c\" /></testsuite>')\n"
            "print('all good, nothing to see here')\n"
            "sys.exit(1)\n",
            encoding="utf-8",
        )

        result = run_check(
            cwd=self.tmp_path,
            check_id="liar-with-artifact",
            command=[sys.executable, str(liar), str(artifact)],
            result_artifact=artifact,
            result_format="junit",
        )

        self.assertEqual(result.exit_code, 1)
        self.assertTrue(result.failed_tests, "artifact claims a clean pass; exit code says otherwise, and exit code must win")

    def test_genuinely_clean_check_passes(self):
        clean = self.tmp_path / "clean.py"
        artifact = self.tmp_path / "results.xml"
        clean.write_text(
            "import sys\n"
            "with open(sys.argv[1], 'w') as f:\n"
            "    f.write('<testsuite><testcase name=\"t\" classname=\"c\" /></testsuite>')\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )

        result = run_check(
            cwd=self.tmp_path,
            check_id="clean",
            command=[sys.executable, str(clean), str(artifact)],
            result_artifact=artifact,
            result_format="junit",
        )

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.failed_tests)

    def test_pre_existing_failure_is_not_a_regression(self):
        baseline = run_check(
            cwd=self.tmp_path,
            check_id="x",
            command=[sys.executable, "-c", "import sys; sys.exit(1)"],
            result_artifact=self.tmp_path / "missing.xml",
            result_format="junit",
        )
        current = run_check(
            cwd=self.tmp_path,
            check_id="x",
            command=[sys.executable, "-c", "import sys; sys.exit(1)"],
            result_artifact=self.tmp_path / "missing.xml",
            result_format="junit",
        )
        self.assertFalse(is_regression(baseline, current))

    def test_toolchain_missing_is_not_run_not_a_pass(self):
        result = run_check(
            cwd=self.tmp_path,
            check_id="missing-tool",
            command=["this-binary-does-not-exist-anywhere"],
            result_artifact=self.tmp_path / "missing.xml",
            result_format="junit",
        )
        self.assertTrue(result.not_run)
        self.assertIsNotNone(result.not_run_reason)


if __name__ == "__main__":
    unittest.main()
