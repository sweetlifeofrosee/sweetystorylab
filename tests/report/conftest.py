"""
tests/report/conftest.py

Shared fixtures. The central one, `git_repo`, builds a real, throwaway
git repository under pytest's tmp_path with a small helper for
committing a file with an explicit (possibly out-of-chronological-
order) commit date -- exactly the scenario that surfaced the real bug
in git_history.py during manual testing.
"""
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest


class GitRepoHelper:
    def __init__(self, root: Path):
        self.root = root

    def _run(self, *args, env_overrides=None):
        import os
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        result = subprocess.run(
            ["git", *args], cwd=str(self.root), capture_output=True, text=True, env=env
        )
        assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
        return result.stdout

    def write(self, relative_path: str, content: str):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, relative_path: str, content: str, when: datetime, message: str = "test commit"):
        """
        Writes `content` to `relative_path` and commits it with an
        explicit author/committer date, which may be earlier or later
        than previous commits -- deliberately, since that's the exact
        condition that matters for the git history logic under test.
        """
        self.write(relative_path, content)
        iso = when.astimezone(timezone.utc).isoformat()
        self._run("add", relative_path)
        self._run(
            "commit", "-m", message,
            env_overrides={"GIT_AUTHOR_DATE": iso, "GIT_COMMITTER_DATE": iso},
        )
        return self._run("rev-parse", "HEAD").strip()

    def head(self) -> str:
        return self._run("rev-parse", "HEAD").strip()


@pytest.fixture
def git_repo(tmp_path) -> GitRepoHelper:
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path), check=True)
    return GitRepoHelper(tmp_path)
