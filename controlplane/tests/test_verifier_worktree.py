"""FRD EXEC-10: the verifier executes against an independent checkout that the implementer
cannot write to. This locks down the actual separation guarantee, not just that the pipeline
still runs end to end."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import gitops  # noqa: E402


class VerifierWorktreeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        gitops.git(self.repo, "init", "-q")
        gitops.git(self.repo, "config", "user.email", "test@local")
        gitops.git(self.repo, "config", "user.name", "test")
        (self.repo / "a.txt").write_text("baseline", encoding="utf-8")
        self.baseline_sha = gitops.commit_all(self.repo, "baseline")
        self.verifier = Path(self._tmp.name) / "verifier"
        gitops.add_worktree(self.repo, self.verifier, self.baseline_sha)

    def tearDown(self):
        gitops.remove_worktree(self.repo, self.verifier)
        self._tmp.cleanup()

    def test_verifier_worktree_is_a_separate_directory(self):
        self.assertNotEqual(self.repo.resolve(), self.verifier.resolve())
        self.assertTrue((self.verifier / "a.txt").exists())

    def test_uncommitted_implementer_edit_is_invisible_to_the_verifier(self):
        """The core guarantee: an in-progress, not-yet-committed edit in the implementer's
        working directory must not be visible from the verifier's worktree at all."""
        (self.repo / "a.txt").write_text("uncommitted implementer edit", encoding="utf-8")

        self.assertEqual((self.verifier / "a.txt").read_text(encoding="utf-8"), "baseline")

    def test_verifier_worktree_advances_only_when_explicitly_checked_out(self):
        (self.repo / "a.txt").write_text("phase edit", encoding="utf-8")
        new_sha = gitops.commit_all(self.repo, "phase: edit a.txt")

        # committed, but the verifier hasn't been told to look yet
        self.assertEqual((self.verifier / "a.txt").read_text(encoding="utf-8"), "baseline")

        gitops.checkout(self.verifier, new_sha)
        self.assertEqual((self.verifier / "a.txt").read_text(encoding="utf-8"), "phase edit")

    def test_deleting_the_run_branch_does_not_touch_a_detached_worktree(self):
        """The verifier is checked out by raw commit SHA, detached — never by branch name — so
        it never blocks or is blocked by branch operations in the main working directory."""
        branch = gitops.create_run_branch(self.repo, "test-run", self.baseline_sha)
        gitops.checkout(self.repo, self.baseline_sha)
        gitops.delete_branch(self.repo, branch)  # must not raise

        self.assertTrue((self.verifier / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()
