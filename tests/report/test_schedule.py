"""
tests/report/test_schedule.py

Covers scripts/report/schedule.py: brand-to-workflow association (via
scanning for `--brand <id>`, not a hardcoded table) and cron-expression
occurrence estimation.
"""
from pathlib import Path

from scripts.report.schedule import (
    _cron_occurrences_per_week,
    find_workflow_for_brand,
    load_planned_schedule,
)


HORROR_WORKFLOW = """\
name: Horror Reels Bot
on:
  schedule:
    - cron: '0 11 * * *'
  workflow_dispatch:
jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - run: python -m core.pipeline.cli --brand horror_lab --db-path horror_log.db
"""

MYSTERY_WORKFLOW = """\
name: Mystery Reels Bot
on:
  schedule:
    - cron: '0 23 * * *'
  workflow_dispatch:
jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - run: python -m core.pipeline.cli --brand mystery_lab --db-path mystery_log.db
"""

WEEKDAY_ONLY_WORKFLOW = """\
name: Weekday Brand Bot
on:
  schedule:
    - cron: '0 9 * * 1,3,5'
jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - run: python -m core.pipeline.cli --brand weekday_brand --db-path weekday.db
"""

UNRELATED_WORKFLOW = """\
name: Weekly Performance Report
on:
  schedule:
    - cron: '0 6 * * 1'
  workflow_dispatch:
jobs:
  weekly-report:
    runs-on: ubuntu-latest
    steps:
      - run: python -m scripts.report.run_weekly_report
"""


def _write_workflows(tmp_path: Path, **named_contents) -> Path:
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    for filename, content in named_contents.items():
        (workflows_dir / filename).write_text(content, encoding="utf-8")
    return workflows_dir


# --- cron occurrence estimation -------------------------------------------

def test_daily_cron_is_seven_per_week():
    assert _cron_occurrences_per_week("0 11 * * *") == 7


def test_weekday_list_cron_counts_days():
    assert _cron_occurrences_per_week("0 9 * * 1,3,5") == 3


def test_specific_day_of_month_returns_none_not_a_guess():
    # Runs on the 1st of the month -- not a steady weekly cadence;
    # the estimator should decline to guess rather than return a
    # misleading number.
    assert _cron_occurrences_per_week("0 9 1 * *") is None


def test_malformed_cron_returns_none():
    assert _cron_occurrences_per_week("not a cron expression") is None


# --- brand -> workflow discovery -------------------------------------------

def test_find_workflow_for_brand_matches_by_flag_not_filename(tmp_path):
    workflows_dir = _write_workflows(
        tmp_path, **{"post.yml": HORROR_WORKFLOW, "post_mystery.yml": MYSTERY_WORKFLOW}
    )
    found = find_workflow_for_brand("mystery_lab", workflows_dir)
    assert found.name == "post_mystery.yml"


def test_find_workflow_for_brand_ignores_unrelated_workflows(tmp_path):
    workflows_dir = _write_workflows(
        tmp_path,
        **{
            "post.yml": HORROR_WORKFLOW,
            "post_mystery.yml": MYSTERY_WORKFLOW,
            "weekly-report.yml": UNRELATED_WORKFLOW,
        },
    )
    # The weekly-report workflow has its own cron and no --brand flag;
    # it must never be mistaken for a brand's posting schedule.
    assert find_workflow_for_brand("horror_lab", workflows_dir).name == "post.yml"
    assert find_workflow_for_brand("weekly_report", workflows_dir) is None


def test_find_workflow_for_brand_returns_none_for_unknown_brand(tmp_path):
    workflows_dir = _write_workflows(tmp_path, **{"post.yml": HORROR_WORKFLOW})
    assert find_workflow_for_brand("nonexistent_brand", workflows_dir) is None


def test_find_workflow_for_brand_returns_none_when_dir_missing(tmp_path):
    assert find_workflow_for_brand("horror_lab", tmp_path / "does-not-exist") is None


# --- load_planned_schedule (integration of the above) -----------------------

def test_load_planned_schedule_daily_brand(tmp_path):
    workflows_dir = _write_workflows(tmp_path, **{"post.yml": HORROR_WORKFLOW})
    schedule = load_planned_schedule("horror_lab", workflows_dir)
    assert schedule.workflow_file == "post.yml"
    assert schedule.cron_expressions == ["0 11 * * *"]
    assert schedule.planned_posts_per_week == 7


def test_load_planned_schedule_weekday_only_brand(tmp_path):
    workflows_dir = _write_workflows(tmp_path, **{"weekday.yml": WEEKDAY_ONLY_WORKFLOW})
    schedule = load_planned_schedule("weekday_brand", workflows_dir)
    assert schedule.planned_posts_per_week == 3


def test_load_planned_schedule_returns_none_for_unmatched_brand(tmp_path):
    workflows_dir = _write_workflows(tmp_path, **{"post.yml": HORROR_WORKFLOW})
    assert load_planned_schedule("mystery_lab", workflows_dir) is None


def test_load_planned_schedule_handles_bare_on_key_yaml_quirk(tmp_path):
    # PyYAML parses an unquoted `on:` key as boolean True under YAML 1.1
    # rules in some configurations -- this must not raise a KeyError.
    workflows_dir = _write_workflows(tmp_path, **{"post_mystery.yml": MYSTERY_WORKFLOW})
    schedule = load_planned_schedule("mystery_lab", workflows_dir)
    assert schedule is not None
    assert schedule.planned_posts_per_week == 7
