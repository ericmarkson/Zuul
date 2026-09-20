"""FRD EXEC-7's lock half. Hermetic -- local filesystem only, no network, no subprocess."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.run_lock import RunLock, RunLockHeld  # noqa: E402


class RunLockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_path = Path(self._tmp.name) / "run.lock"

    def tearDown(self):
        self._tmp.cleanup()

    def test_acquire_and_release_round_trips(self):
        lock = RunLock(self.lock_path)
        lock.acquire()
        lock.release()  # must not raise

    def test_second_lock_on_same_path_is_refused_while_first_is_held(self):
        first = RunLock(self.lock_path)
        first.acquire()
        try:
            second = RunLock(self.lock_path)
            with self.assertRaises(RunLockHeld):
                second.acquire()
        finally:
            first.release()

    def test_lock_is_acquirable_again_after_release(self):
        first = RunLock(self.lock_path)
        first.acquire()
        first.release()

        second = RunLock(self.lock_path)
        second.acquire()  # must not raise -- the path is free again
        second.release()

    def test_works_as_a_context_manager(self):
        with RunLock(self.lock_path):
            second = RunLock(self.lock_path)
            with self.assertRaises(RunLockHeld):
                second.acquire()
        # released on context exit
        third = RunLock(self.lock_path)
        third.acquire()
        third.release()

    def test_release_before_acquire_is_a_harmless_no_op(self):
        lock = RunLock(self.lock_path)
        lock.release()  # must not raise


if __name__ == "__main__":
    unittest.main()
