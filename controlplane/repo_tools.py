"""Read-only, repo-confined tools shared by every bounded tool-calling loop in this project --
the plan-generation researcher (`plangen_llm.py`) and the phase implementer
(`llm_implementer.py`). FRD EXEC-2 stays honest for both: everything here only reads, never
writes, and every path is confined to the target repo by `resolve_within_repo`'s
path-traversal guard -- there is no reason either loop should ever see outside the repo it was
handed, and this is the one place that guarantee is implemented, so both loops share it rather
than each keeping (and potentially drifting) their own copy."""

from __future__ import annotations

from pathlib import Path

IGNORED_DIR_NAMES = {"bin", "obj", ".git", "node_modules", "__pycache__"}


def resolve_within_repo(target_repo: Path, rel_path: str) -> Path | None:
    """None means "refuse," not "raise" -- a misbehaving tool call becomes an error string fed
    back to the model, not a crashed run."""
    candidate = (target_repo / rel_path).resolve()
    repo_root = target_repo.resolve()
    if candidate != repo_root and repo_root not in candidate.parents:
        return None
    return candidate


def read_file_tool(target_repo: Path, path: str) -> str:
    resolved = resolve_within_repo(target_repo, path)
    if resolved is None:
        return "error: path is outside the target repository"
    if not resolved.is_file():
        return "error: no such file"
    return resolved.read_text(encoding="utf-8", errors="replace")


def list_directory_tool(target_repo: Path, path: str) -> str:
    resolved = resolve_within_repo(target_repo, path)
    if resolved is None:
        return "error: path is outside the target repository"
    if not resolved.is_dir():
        return "error: no such directory"
    return "\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in resolved.iterdir()))


def grep_repo_tool(target_repo: Path, pattern: str, path_glob: str | None = None, max_matches: int = 50) -> str:
    """A plain, case-insensitive substring search across the repo's text files -- not a regex
    engine, deliberately: this is meant to answer "does this identifier show up anywhere the
    audit's findings didn't already mention," not to be a general-purpose search tool, and a
    literal substring match has no ReDoS/injection surface to worry about."""
    if not target_repo.is_dir():
        return "error: target repository not found"
    if not pattern:
        return "error: empty pattern"
    try:
        candidates = sorted(target_repo.glob(path_glob or "**/*"))
    except ValueError as exc:
        return f"error: invalid path_glob: {exc}"

    pattern_lower = pattern.lower()
    matches: list[str] = []
    for path in candidates:
        if not path.is_file() or any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(target_repo).as_posix()
        for line_no, line in enumerate(text.splitlines(), 1):
            if pattern_lower in line.lower():
                matches.append(f"{rel}:{line_no}: {line.strip()}")
                if len(matches) >= max_matches:
                    return "\n".join(matches) + f"\n... (truncated at {max_matches} matches)"
    return "\n".join(matches) if matches else "no matches found"
