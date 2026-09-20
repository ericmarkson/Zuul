"""FRD EXEC-7's resume-report half. Hermetic -- writes its own event log fixtures, no network."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import gitops  # noqa: E402
from controlplane.resume import build_resume_report, is_incomplete  # noqa: E402


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


class ResumeDetectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.event_log_path = Path(self._tmp.name) / "events.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_nonexistent_log_is_not_incomplete(self):
        self.assertFalse(is_incomplete(self.event_log_path))

    def test_log_ending_without_a_terminal_event_is_incomplete(self):
        _write_log(self.event_log_path, [
            {"event_type": "RUN_STARTED"},
            {"event_type": "BASELINE_CAPTURED"},
            {"event_type": "PHASE_STARTED", "phase_id": "phase-1"},
        ])
        self.assertTrue(is_incomplete(self.event_log_path))

    def test_log_ending_in_run_completed_is_not_incomplete(self):
        _write_log(self.event_log_path, [{"event_type": "RUN_STARTED"}, {"event_type": "RUN_COMPLETED"}])
        self.assertFalse(is_incomplete(self.event_log_path))

    def test_log_ending_in_escalated_is_not_incomplete(self):
        _write_log(self.event_log_path, [{"event_type": "RUN_STARTED"}, {"event_type": "ESCALATED"}])
        self.assertFalse(is_incomplete(self.event_log_path))

    def test_log_ending_in_run_abandoned_is_not_incomplete(self):
        _write_log(self.event_log_path, [{"event_type": "RUN_STARTED"}, {"event_type": "RUN_ABANDONED"}])
        self.assertFalse(is_incomplete(self.event_log_path))


class ResumeReportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.event_log_path = Path(self._tmp.name) / "events.jsonl"
        self.target_repo = Path(self._tmp.name) / "target"

    def tearDown(self):
        self._tmp.cleanup()

    def test_report_finds_last_committed_phase(self):
        _write_log(self.event_log_path, [
            {"event_type": "RUN_STARTED"},
            {"event_type": "PHASE_COMMITTED", "phase_id": "phase-1", "commit": "aaa"},
            {"event_type": "PHASE_STARTED", "phase_id": "phase-2"},
        ])
        report = build_resume_report("test-run", self.event_log_path, self.target_repo)
        self.assertEqual(report.last_committed_phase["phase_id"], "phase-1")
        self.assertEqual(report.last_event["event_type"], "PHASE_STARTED")
        self.assertEqual(report.total_events, 3)

    def test_report_with_no_phase_committed_yet(self):
        _write_log(self.event_log_path, [{"event_type": "RUN_STARTED"}])
        report = build_resume_report("test-run", self.event_log_path, self.target_repo)
        self.assertIsNone(report.last_committed_phase)

    def test_report_reads_real_git_state_when_target_repo_exists(self):
        self.target_repo.mkdir()
        gitops.git(self.target_repo, "init", "-q")
        gitops.git(self.target_repo, "config", "user.email", "test@local")
        gitops.git(self.target_repo, "config", "user.name", "test")
        (self.target_repo / "a.txt").write_text("baseline", encoding="utf-8")
        gitops.commit_all(self.target_repo, "baseline")
        gitops.create_run_branch(self.target_repo, "test-run", gitops.head(self.target_repo))

        _write_log(self.event_log_path, [{"event_type": "RUN_STARTED"}])
        report = build_resume_report("test-run", self.event_log_path, self.target_repo)

        self.assertIsNotNone(report.run_branch_head)
        self.assertFalse(report.target_repo_dirty)

    def test_report_flags_a_dirty_working_tree(self):
        self.target_repo.mkdir()
        gitops.git(self.target_repo, "init", "-q")
        gitops.git(self.target_repo, "config", "user.email", "test@local")
        gitops.git(self.target_repo, "config", "user.name", "test")
        (self.target_repo / "a.txt").write_text("baseline", encoding="utf-8")
        gitops.commit_all(self.target_repo, "baseline")
        (self.target_repo / "a.txt").write_text("uncommitted change", encoding="utf-8")

        _write_log(self.event_log_path, [{"event_type": "RUN_STARTED"}])
        report = build_resume_report("test-run", self.event_log_path, self.target_repo)

        self.assertTrue(report.target_repo_dirty)


if __name__ == "__main__":
    unittest.main()
