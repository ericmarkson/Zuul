"""FRD INTEGRITY-1: halt on a dirty tree rather than stash/commit/discard it."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import gitops  # noqa: E402


def _init_repo(path: Path) -> None:
    gitops.git(path, "init", "-q")
    gitops.git(path, "config", "user.email", "test@local")
    gitops.git(path, "config", "user.name", "test")


class BaselineCaptureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        _init_repo(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_captures_baseline(self):
        (self.repo / "a.txt").write_text("hello", encoding="utf-8")
        gitops.commit_all(self.repo, "initial")
        sha = gitops.capture_baseline(self.repo)
        self.assertEqual(len(sha), 40)

    def test_dirty_tree_refuses_rather_than_discarding_work(self):
        (self.repo / "a.txt").write_text("hello", encoding="utf-8")
        gitops.commit_all(self.repo, "initial")
        (self.repo / "a.txt").write_text("uncommitted change", encoding="utf-8")

        with self.assertRaises(gitops.DirtyTreeError):
            gitops.capture_baseline(self.repo)

        # the uncommitted change must still be there — nothing was stashed or discarded
        self.assertEqual((self.repo / "a.txt").read_text(encoding="utf-8"), "uncommitted change")

    def test_run_branch_never_touches_a_pre_existing_branch(self):
        (self.repo / "a.txt").write_text("hello", encoding="utf-8")
        gitops.commit_all(self.repo, "initial")
        baseline_sha = gitops.capture_baseline(self.repo)
        starting_branch = gitops.git(self.repo, "branch", "--show-current").stdout.strip()

        gitops.create_run_branch(self.repo, "test-run-1", baseline_sha)

        # the pre-existing branch's tip must be unchanged
        pre_existing_tip = gitops.git(self.repo, "rev-parse", starting_branch).stdout.strip()
        self.assertEqual(pre_existing_tip, baseline_sha)


if __name__ == "__main__":
    unittest.main()
