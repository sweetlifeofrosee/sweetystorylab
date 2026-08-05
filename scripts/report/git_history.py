"""
scripts/report/git_history.py

Small, dependency-free wrapper around `git log` / `git show`, used to
derive *weekly* deltas from files that the production pipeline already
commits to the repo (today: brands/mystery_lab/used_subjects.json),
without requiring any change to that pipeline.

Why this exists: the repo does not currently persist a per-post,
timestamped operational log (see the Architecture and Development
Guide §7 and §12 -- that log is artifact-only, 30-day retention, for
both brands). What the repo *does* have is a file that gets committed
exactly when something meaningful happens (a new subject is accepted).
Git's own commit history on that file is therefore a legitimate,
repository-first source of "what happened, and when" -- we're reading
existing commit metadata, not adding new instrumentation.

This module is intentionally generic: it operates on "a file's commit
history in a date window," not on used_subjects.json specifically.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import subprocess


class GitHistoryError(Exception):
    """Raised when the underlying git command fails unexpectedly."""


@dataclass
class Commit:
    sha: str
    date: datetime  # commit date, timezone-aware (from git's %cI)
    message: str


def _run_git(args: List[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitHistoryError(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}"
        )
    return result.stdout


def is_git_repo(repo_root: Path) -> bool:
    try:
        _run_git(["rev-parse", "--is-inside-work-tree"], cwd=repo_root)
        return True
    except GitHistoryError:
        return False


def commits_touching_file(
    relative_path: str,
    repo_root: Path,
    since: datetime,
    until: datetime,
) -> List[Commit]:
    """
    Commits that touched `relative_path`, with commit date in
    [since, until). Oldest first. Returns [] if the path has no
    history yet (e.g. brand-new file, or file doesn't exist), rather
    than raising -- an empty result is a normal, expected state here.

    Deliberately does NOT use `git log --since/--until`: those flags
    assume commits are encountered in strictly descending date order
    during traversal and stop walking as soon as they see one outside
    the window. That assumption doesn't always hold (rebases, restored
    history, clock skew, or -- as found while testing this module --
    any commit whose date was set out of order for any reason), and a
    silent early stop would under-report real weekly activity without
    any error. Instead, the full commit list for this path is fetched
    once and filtered by date in Python, which is correct regardless
    of traversal order.
    """
    try:
        output = _run_git(
            [
                "log",
                "--date=iso-strict",
                "--format=%H|%cI|%s",
                "--",
                relative_path,
            ],
            cwd=repo_root,
        )
    except GitHistoryError:
        return []

    commits = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        sha, date_iso, message = line.split("|", 2)
        commit_date = datetime.fromisoformat(date_iso)
        if since <= commit_date < until:
            commits.append(Commit(sha=sha, date=commit_date, message=message))
    commits.sort(key=lambda c: c.date)  # oldest first
    return commits


def file_content_at_commit(relative_path: str, sha: str, repo_root: Path) -> Optional[str]:
    """
    Content of `relative_path` as of commit `sha`, or None if the path
    didn't exist at that commit (e.g. the commit that introduced it).
    """
    try:
        return _run_git(["show", f"{sha}:{relative_path}"], cwd=repo_root)
    except GitHistoryError:
        return None


def parent_of(sha: str, repo_root: Path) -> Optional[str]:
    """The first parent's SHA, or None if `sha` is the repo's first commit."""
    try:
        output = _run_git(["rev-list", "--parents", "-n", "1", sha], cwd=repo_root)
    except GitHistoryError:
        return None
    parts = output.strip().split()
    return parts[1] if len(parts) > 1 else None
