"""
tests/report/test_editorial_history.py

Covers scripts/report/editorial_history.py: the honest
available/unavailable distinction, the used_subjects.json shape
({"used_subjects": [...]}), and weekly-delta derivation via git.
"""
from datetime import datetime, timezone
import json

from scripts.report.editorial_history import load_editorial_history, _load_subjects_set


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


# --- _load_subjects_set: real on-disk shape handling ------------------------

def test_load_subjects_set_handles_real_dict_shape():
    raw = json.dumps({"used_subjects": ["Dogon Tribe", "Tanis"]})
    assert _load_subjects_set(raw) == {"Dogon Tribe", "Tanis"}


def test_load_subjects_set_handles_bare_list_shape():
    raw = json.dumps(["A", "B"])
    assert _load_subjects_set(raw) == {"A", "B"}


def test_load_subjects_set_handles_missing_content():
    assert _load_subjects_set(None) == set()


def test_load_subjects_set_handles_malformed_json():
    assert _load_subjects_set("{not valid json") == set()


def test_load_subjects_set_handles_unexpected_shape():
    assert _load_subjects_set(json.dumps({"something_else": 1})) == set()


# --- load_editorial_history: brand with no dedup file -----------------------

def test_brand_with_no_used_subjects_file_is_unavailable(tmp_path):
    brand_dir = tmp_path / "brands" / "horror_lab"
    brand_dir.mkdir(parents=True)
    # No git repo at all, and no used_subjects.json -- mirrors Horror
    # Lab's actual real-world state (confirmed by the architecture audit).
    result = load_editorial_history(
        "horror_lab", brand_dir, tmp_path, _dt("2026-07-28T00:00:00"), _dt("2026-08-04T00:00:00")
    )
    assert result.available is False
    assert result.unavailable_reason is not None
    assert "used_subjects.json" in result.unavailable_reason
    assert result.weekly_new_subjects == []
    assert result.weekly_commit_count == 0


# --- load_editorial_history: brand with the file, no git repo ---------------

def test_brand_with_file_but_no_git_repo_reports_cumulative_only(tmp_path):
    brand_dir = tmp_path / "brands" / "mystery_lab"
    brand_dir.mkdir(parents=True)
    (brand_dir / "used_subjects.json").write_text(
        json.dumps({"used_subjects": ["A", "B", "C"]}), encoding="utf-8"
    )
    # tmp_path is not a git repo.
    result = load_editorial_history(
        "mystery_lab", brand_dir, tmp_path, _dt("2026-07-28T00:00:00"), _dt("2026-08-04T00:00:00")
    )
    assert result.available is True
    assert result.cumulative_subjects_count == 3
    assert result.weekly_new_subjects == []
    assert result.weekly_commit_count == 0


# --- load_editorial_history: full git-backed weekly derivation --------------

def test_brand_with_git_history_derives_weekly_delta(git_repo):
    brand_dir = git_repo.root / "brands" / "mystery_lab"
    rel_path = "brands/mystery_lab/used_subjects.json"

    # Before the report window: two subjects already known.
    git_repo.commit(rel_path, json.dumps({"used_subjects": ["A", "B"]}), _dt("2026-07-20T12:00:00"))

    # Two accepted posts land inside the report window.
    git_repo.commit(
        rel_path, json.dumps({"used_subjects": ["A", "B", "C"]}), _dt("2026-07-29T23:05:00")
    )
    git_repo.commit(
        rel_path, json.dumps({"used_subjects": ["A", "B", "C", "D"]}), _dt("2026-08-01T23:05:00")
    )

    # One more lands after the window closes -- must not be counted.
    git_repo.commit(
        rel_path, json.dumps({"used_subjects": ["A", "B", "C", "D", "E"]}), _dt("2026-08-10T23:05:00")
    )

    result = load_editorial_history(
        "mystery_lab", brand_dir, git_repo.root, _dt("2026-07-28T00:00:00"), _dt("2026-08-04T23:59:59")
    )

    assert result.available is True
    assert result.weekly_new_subjects == ["C", "D"]
    assert result.weekly_commit_count == 2
    assert result.cumulative_subjects_count == 5  # reflects current on-disk state, not the window


def test_brand_with_no_activity_in_window_reports_zero_not_unavailable(git_repo):
    brand_dir = git_repo.root / "brands" / "mystery_lab"
    rel_path = "brands/mystery_lab/used_subjects.json"
    git_repo.commit(rel_path, json.dumps({"used_subjects": ["A"]}), _dt("2026-01-01T00:00:00"))

    result = load_editorial_history(
        "mystery_lab", brand_dir, git_repo.root, _dt("2026-07-28T00:00:00"), _dt("2026-08-04T00:00:00")
    )

    # The file (and repo-side signal) genuinely exists -- this is a
    # real, quiet week, not a missing data source. available=True with
    # weekly_commit_count=0 is the correct, distinct outcome from the
    # "no file at all" case above.
    assert result.available is True
    assert result.weekly_new_subjects == []
    assert result.weekly_commit_count == 0
    assert result.cumulative_subjects_count == 1


def test_editorial_intelligence_fields_not_yet_captured_are_empty(git_repo):
    # No brand in the real repo captures category/theme/hook data yet
    # (confirmed by the architecture audit) -- these fields must exist
    # on the result and be empty, not populated with placeholder data.
    brand_dir = git_repo.root / "brands" / "mystery_lab"
    rel_path = "brands/mystery_lab/used_subjects.json"
    git_repo.commit(rel_path, json.dumps({"used_subjects": ["A"]}), _dt("2026-07-29T00:00:00"))

    result = load_editorial_history(
        "mystery_lab", brand_dir, git_repo.root, _dt("2026-07-28T00:00:00"), _dt("2026-08-04T00:00:00")
    )

    assert result.weekly_categories == []
    assert result.weekly_themes == []
    assert result.weekly_hooks == []


# --- Windows path-separator regression -------------------------------------
#
# Real bug found in the field (Windows, git-bash): a brand path more than
# one directory deep produced weekly_new_subjects == [] instead of the
# real delta, while the exact same scenario passed on Linux/macOS. Root
# cause: editorial_history.py built the git pathspec via str(Path.relative_to(...)),
# which on Windows yields backslash-separated segments; git's pathspec
# parser treats backslash as an escape character, silently breaking the
# match for any nested path (a flat filename has no separator to mangle,
# which is why the single-file git_history.py tests didn't catch this).
# Fixed by using .as_posix() instead of str(). This test simulates
# Windows' path semantics directly (via PureWindowsPath) so the
# regression is caught on any platform running the suite, not only on
# Windows.

def test_relative_path_construction_uses_forward_slashes_even_on_windows():
    from pathlib import PureWindowsPath

    windows_subjects_path = PureWindowsPath(r"C:\repo\brands\mystery_lab\used_subjects.json")
    windows_repo_root = PureWindowsPath(r"C:\repo")

    # This is the exact expression editorial_history.py now uses.
    relative_path = windows_subjects_path.relative_to(windows_repo_root).as_posix()

    assert relative_path == "brands/mystery_lab/used_subjects.json"
    assert "\\" not in relative_path


def test_load_editorial_history_source_uses_as_posix_not_str():
    """
    Belt-and-suspenders guard for the same bug, at the actual call site.

    The test above proves .as_posix() is the *right* expression, but it
    can't prove load_editorial_history() actually *uses* it: on Linux,
    str(Path.relative_to(...)) and .as_posix() produce identical output
    (POSIX paths already use forward slashes), so a Linux test runner
    can exercise the buggy version end-to-end and see no failure --
    which is exactly why this shipped without being caught the first
    time. This test reads the real source and asserts the fixed
    expression is actually there, since this sandbox cannot construct a
    real WindowsPath to exercise the bug behaviorally. Windows CI (or a
    Windows machine) remains the authoritative check.
    """
    import inspect
    from scripts.report import editorial_history

    source = inspect.getsource(editorial_history.load_editorial_history)
    assert ".relative_to(repo_root).as_posix()" in source
    assert "str(subjects_path.relative_to(repo_root))" not in source
