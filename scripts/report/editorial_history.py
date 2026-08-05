"""
scripts/report/editorial_history.py

Repository-first editorial history loader -- the primary (required)
data source per the approved v1.3 architecture (Guide §14.3).

What actually exists in the repo today (confirmed by direct audit,
Guide §5/§7), and what this module honestly does with it:

  - brands/mystery_lab/used_subjects.json: a flat, cumulative,
    UN-timestamped list of subjects Mystery Lab has used. There is no
    per-subject date in the file itself. To get a *weekly* view, this
    module reads the file's own git commit history (see git_history.py)
    and diffs each in-window commit against its parent to recover which
    subject(s) were added in that commit -- this works because
    post_mystery.yml only commits the file when it actually changes
    (one accepted, non-duplicate story = one changed subject = one
    commit). See schedule.py / git_history.py docstrings for more.

  - brands/horror_lab has no equivalent file at all. Horror Lab has
    zero repository-side editorial signal today. This module reports
    that honestly (available=False) rather than fabricating data or
    silently omitting the brand.

  - No brand has category, theme, or hook fields anywhere in the repo
    (confirmed against core/story/schema.py and both parser.py files).
    Those Editorial Intelligence fields from the approved design
    (best-performing categories/themes/top hooks, category frequency)
    have no data source yet -- this is stated explicitly in the
    rendered report (Guide §14.4's note on this exact gap), not
    silently dropped or stubbed with fake values.

This module is read-only: it never writes to used_subjects.json or
any other brand-owned file.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import json

from . import git_history

SUBJECTS_FILENAME = "used_subjects.json"


@dataclass
class EditorialHistory:
    brand_id: str
    available: bool
    unavailable_reason: Optional[str] = None

    # Cumulative, all-time state (only meaningful if available=True)
    cumulative_subjects_count: Optional[int] = None

    # This week's delta, derived from git history (only meaningful if
    # available=True)
    weekly_new_subjects: List[str] = field(default_factory=list)
    weekly_commit_count: int = 0  # proxy for "accepted posts this week"

    # No brand captures these yet anywhere in the repo -- always empty
    # in V1. Kept as explicit fields (rather than omitted) so
    # render_report.py has one obvious place to check "is this
    # populated yet" as the schema work in Guide §12 lands.
    weekly_categories: List[str] = field(default_factory=list)
    weekly_themes: List[str] = field(default_factory=list)
    weekly_hooks: List[str] = field(default_factory=list)


def _load_subjects_set(raw_text: Optional[str]) -> set:
    """
    Parses used_subjects.json's actual on-disk shape:
    {"used_subjects": ["Subject A", "Subject B", ...]}
    Defensively handles a bare list too, in case the format is ever
    simplified. Returns an empty set for missing/unparseable content
    rather than raising -- a git revision that predates the file, or a
    momentarily malformed commit, shouldn't crash the whole report.
    """
    if not raw_text:
        return set()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return set()
    if isinstance(parsed, dict):
        return set(parsed.get("used_subjects", []))
    if isinstance(parsed, list):
        return set(parsed)
    return set()


def load_editorial_history(
    brand_id: str,
    brand_dir: Path,
    repo_root: Path,
    week_start: datetime,
    week_end: datetime,
) -> EditorialHistory:
    subjects_path = brand_dir / SUBJECTS_FILENAME

    if not subjects_path.exists():
        return EditorialHistory(
            brand_id=brand_id,
            available=False,
            unavailable_reason=(
                f"No {SUBJECTS_FILENAME} found for this brand. This brand has no "
                f"repository-side editorial memory yet (no dedup module configured "
                f"-- see Guide §7's content.dedup_module field)."
            ),
        )

    current_set = _load_subjects_set(subjects_path.read_text(encoding="utf-8"))

    if not git_history.is_git_repo(repo_root):
        # Still report cumulative state -- just can't compute a weekly
        # delta without git history available.
        return EditorialHistory(
            brand_id=brand_id,
            available=True,
            unavailable_reason=None,
            cumulative_subjects_count=len(current_set),
            weekly_new_subjects=[],
            weekly_commit_count=0,
        )

    # NOTE: must be .as_posix(), not str(). On Windows, str(Path.relative_to(...))
    # returns backslash-separated segments (e.g. "brands\mystery_lab\used_subjects.json").
    # Git's pathspec parser treats backslash as an escape character, which silently
    # mangles nested paths passed to `git log`/`git show -- <path>` -- flat filenames
    # are unaffected (no separator to mangle), which is why this only breaks on
    # brand paths with subdirectories. .as_posix() always yields forward slashes
    # regardless of platform, which is what git expects on every OS, including Windows.
    relative_path = subjects_path.relative_to(repo_root).as_posix()
    commits = git_history.commits_touching_file(relative_path, repo_root, week_start, week_end)

    weekly_new = set()
    for commit in commits:
        after_text = git_history.file_content_at_commit(relative_path, commit.sha, repo_root)
        after_set = _load_subjects_set(after_text)

        parent_sha = git_history.parent_of(commit.sha, repo_root)
        if parent_sha:
            before_text = git_history.file_content_at_commit(relative_path, parent_sha, repo_root)
            before_set = _load_subjects_set(before_text)
        else:
            before_set = set()

        weekly_new |= (after_set - before_set)

    return EditorialHistory(
        brand_id=brand_id,
        available=True,
        unavailable_reason=None,
        cumulative_subjects_count=len(current_set),
        weekly_new_subjects=sorted(weekly_new),
        weekly_commit_count=len(commits),
    )
