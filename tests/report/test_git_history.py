"""
tests/report/test_git_history.py

Covers scripts/report/git_history.py's commit-window logic. The most
important test here (test_out_of_order_commit_dates_are_still_windowed_
correctly) is a direct regression test for a real bug found while
manually testing the module: `git log --since/--until` stops walking
as soon as it sees a commit outside the window, which silently
under-counts real activity if commits aren't in strict date order.
"""
from datetime import datetime, timedelta, timezone

from scripts.report import git_history


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def test_is_git_repo_true_for_real_repo(git_repo):
    assert git_history.is_git_repo(git_repo.root) is True


def test_is_git_repo_false_for_non_repo(tmp_path_factory):
    non_repo = tmp_path_factory.mktemp("not-a-repo")
    assert git_history.is_git_repo(non_repo) is False


def test_commits_touching_file_empty_when_no_history(git_repo):
    commits = git_history.commits_touching_file(
        "nonexistent.json", git_repo.root, _dt("2026-01-01T00:00:00"), _dt("2026-01-08T00:00:00")
    )
    assert commits == []


def test_commits_touching_file_filters_to_window(git_repo):
    git_repo.commit("data.json", '{"v": 1}', _dt("2026-07-20T12:00:00"))
    in_window_sha = git_repo.commit("data.json", '{"v": 2}', _dt("2026-07-29T12:00:00"))
    git_repo.commit("data.json", '{"v": 3}', _dt("2026-08-10T12:00:00"))  # after window

    commits = git_history.commits_touching_file(
        "data.json", git_repo.root, _dt("2026-07-28T00:00:00"), _dt("2026-08-04T00:00:00")
    )

    assert [c.sha for c in commits] == [in_window_sha]


def test_commits_touching_file_returns_oldest_first(git_repo):
    sha1 = git_repo.commit("data.json", '{"v": 1}', _dt("2026-07-28T01:00:00"))
    sha2 = git_repo.commit("data.json", '{"v": 2}', _dt("2026-07-29T01:00:00"))
    sha3 = git_repo.commit("data.json", '{"v": 3}', _dt("2026-07-30T01:00:00"))

    commits = git_history.commits_touching_file(
        "data.json", git_repo.root, _dt("2026-07-28T00:00:00"), _dt("2026-08-04T00:00:00")
    )

    assert [c.sha for c in commits] == [sha1, sha2, sha3]


def test_out_of_order_commit_dates_are_still_windowed_correctly(git_repo):
    """
    Regression test: a commit whose date is EARLIER than its parent's
    (simulating clock skew, a backdated commit, or any history where
    git's traversal order and date order diverge) must not cause
    later, genuinely in-window commits to be silently dropped.

    This reproduces the exact bug found manually: the original
    implementation used `git log --since/--until`, which stopped
    walking as soon as it saw the out-of-order commit and returned an
    empty result even though three real in-window commits existed.
    """
    # HEAD's own commit date is BEFORE the window, even though it's
    # the most recently created commit (walked first by git log).
    git_repo.commit("used_subjects.json", '{"used_subjects": []}', _dt("2026-07-15T23:05:00"))

    week_start = _dt("2026-07-28T00:00:00")
    week_end = _dt("2026-08-04T23:59:59")

    sha_a = git_repo.commit(
        "used_subjects.json", '{"used_subjects": ["A"]}', _dt("2026-07-29T23:05:00")
    )
    sha_b = git_repo.commit(
        "used_subjects.json", '{"used_subjects": ["A", "B"]}', _dt("2026-07-31T23:05:00")
    )
    sha_c = git_repo.commit(
        "used_subjects.json", '{"used_subjects": ["A", "B", "C"]}', _dt("2026-08-02T23:05:00")
    )
    # Made last (walked first by git log), but dated before the window --
    # this is the commit that triggered the original bug.
    git_repo.commit(
        "used_subjects.json", '{"used_subjects": ["A", "B", "C", "OLD"]}', _dt("2026-07-15T23:06:00")
    )

    commits = git_history.commits_touching_file(
        "used_subjects.json", git_repo.root, week_start, week_end
    )

    assert {c.sha for c in commits} == {sha_a, sha_b, sha_c}


def test_file_content_at_commit_returns_content(git_repo):
    sha = git_repo.commit("data.json", '{"v": 42}', _dt("2026-07-28T00:00:00"))
    content = git_history.file_content_at_commit("data.json", sha, git_repo.root)
    assert content == '{"v": 42}'


def test_file_content_at_commit_returns_none_before_file_existed(git_repo):
    git_repo.commit("other.json", "{}", _dt("2026-07-27T00:00:00"))
    sha_before_data_json_existed = git_repo.head()
    content = git_history.file_content_at_commit("data.json", sha_before_data_json_existed, git_repo.root)
    assert content is None


def test_parent_of_returns_none_for_root_commit(git_repo):
    sha = git_repo.commit("data.json", "{}", _dt("2026-07-28T00:00:00"))
    assert git_history.parent_of(sha, git_repo.root) is None


def test_parent_of_returns_parent_sha(git_repo):
    sha1 = git_repo.commit("data.json", '{"v": 1}', _dt("2026-07-28T00:00:00"))
    sha2 = git_repo.commit("data.json", '{"v": 2}', _dt("2026-07-29T00:00:00"))
    assert git_history.parent_of(sha2, git_repo.root) == sha1
