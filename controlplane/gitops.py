"""Git primitives — FRD INTEGRITY-1 (baseline, refuse a dirty tree), INTEGRITY-2 (one commit per
phase), INTEGRITY-9 (dedicated run branch, never touch a pre-existing one, never push)."""

from __future__ import annotations

import subprocess
from pathlib import Path


class DirtyTreeError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = _run(["git", *args], cwd)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}")
    return result


def assert_clean_tree(repo: Path) -> None:
    result = git(repo, "status", "--porcelain")
    if result.stdout.strip():
        raise DirtyTreeError(f"target repo has uncommitted changes:\n{result.stdout}")


def capture_baseline(repo: Path) -> str:
    """INTEGRITY-1: record the baseline commit; halt (raise) rather than stash/discard if dirty."""
    assert_clean_tree(repo)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def create_run_branch(repo: Path, run_id: str, baseline_sha: str) -> str:
    """INTEGRITY-9: dedicated branch off the baseline commit, named deterministically from run id."""
    branch = f"run/{run_id}"
    git(repo, "branch", branch, baseline_sha)
    git(repo, "checkout", "-q", branch)
    return branch


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message, "--allow-empty")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def changed_paths(repo: Path, from_sha: str, to_sha: str = "HEAD") -> list[str]:
    result = git(repo, "diff", "--name-only", from_sha, to_sha)
    return [line for line in result.stdout.splitlines() if line]


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def checkout(repo: Path, ref: str) -> None:
    git(repo, "checkout", "-q", ref)


def delete_branch(repo: Path, branch: str) -> None:
    git(repo, "branch", "-D", branch)


def add_worktree(repo: Path, worktree_path: Path, commit: str) -> None:
    """EXEC-10: an independent checkout of a commit, in its own working directory, sharing the
    same underlying .git store. Checked out detached (by raw commit, not by branch name) so it
    never collides with whatever branch is checked out in the main working directory."""
    git(repo, "worktree", "add", "--detach", "-q", str(worktree_path), commit)


def remove_worktree(repo: Path, worktree_path: Path) -> None:
    git(repo, "worktree", "remove", "--force", str(worktree_path), check=False)
