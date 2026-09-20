"""FRD EXEC-7's lock half: an exclusive lock keyed to run id, held for the process's lifetime.
Uses the OS's own advisory file locking (msvcrt on Windows, fcntl elsewhere) rather than a
plain "does this file exist" check, specifically because the OS releases the lock automatically
when the holding process dies -- including a crash -- which a bare marker file cannot do."""

from __future__ import annotations

import os
import sys
from pathlib import Path


class RunLockHeld(RuntimeError):
    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"run lock already held: {path} (a process is already working this run id)")


class RunLock:
    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise RunLockHeld(self.path) from exc

        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()
