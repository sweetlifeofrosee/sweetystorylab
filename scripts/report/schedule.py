"""
scripts/report/schedule.py

Derives each brand's *planned* weekly posting cadence directly from its
GitHub Actions workflow file, rather than hardcoding a brand -> cadence
mapping. This mirrors the Architecture and Development Guide's own note
(§7): scheduling is "owned entirely by the GitHub Actions cron trigger,"
not by brand config.yaml (schedule.times_pht is present in both brands'
config today but currently empty for both).

Brand -> workflow association is done generically by scanning each
workflow's run step for `--brand <brand_id>` (the same flag every
brand's workflow already passes to core.pipeline.cli), rather than by
a hardcoded {"horror_lab": "post.yml", ...} table. This keeps the
report working unmodified if a workflow file is renamed, or if a third
brand is added later with its own workflow file, per the platform's
"will this still work with 50 brands?" design goal.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import re

import yaml

_BRAND_FLAG_RE = re.compile(r"--brand[= ]+([A-Za-z0-9_\-]+)")


@dataclass
class PlannedSchedule:
    workflow_file: str
    cron_expressions: list  # raw cron strings, for display/debugging
    planned_posts_per_week: Optional[int]  # None if it couldn't be estimated


def _cron_occurrences_per_week(cron_expr: str) -> Optional[int]:
    """
    Rough, conservative estimate of how many times a 5-field cron
    expression fires per week. Handles the common cases this platform
    actually uses (daily, or specific weekdays) without attempting to
    be a full cron-semantics engine -- if the expression is something
    this can't confidently interpret, it returns None rather than
    guessing.
    """
    fields = cron_expr.split()
    if len(fields) != 5:
        return None
    _minute, _hour, day_of_month, _month, day_of_week = fields

    if day_of_month != "*":
        # Runs on specific calendar day(s) of the month -- not a
        # steady weekly cadence; don't guess.
        return None

    if day_of_week.strip() == "*":
        return 7  # every day
    # Comma-separated weekday list, e.g. "1,3,5"
    days = [d for d in day_of_week.split(",") if d.strip() != ""]
    if days and all(d.strip().lstrip("-").isdigit() for d in days):
        return len(days)
    return None


def find_workflow_for_brand(brand_id: str, workflows_dir: Path) -> Optional[Path]:
    if not workflows_dir.exists():
        return None
    for wf_path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        text = wf_path.read_text(encoding="utf-8")
        match = _BRAND_FLAG_RE.search(text)
        if match and match.group(1) == brand_id:
            return wf_path
    return None


def load_planned_schedule(brand_id: str, workflows_dir: Path) -> Optional[PlannedSchedule]:
    wf_path = find_workflow_for_brand(brand_id, workflows_dir)
    if wf_path is None:
        return None

    with open(wf_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # YAML parses the `on:` key as boolean True in some PyYAML/YAML
    # 1.1 edge cases; guard for both `on` and the literal True key.
    on_section = raw.get("on", raw.get(True, {})) or {}
    schedule_entries = on_section.get("schedule", []) or []
    cron_exprs = [entry["cron"] for entry in schedule_entries if "cron" in entry]

    weekly_total = 0
    all_estimated = True
    for expr in cron_exprs:
        occurrences = _cron_occurrences_per_week(expr)
        if occurrences is None:
            all_estimated = False
            continue
        weekly_total += occurrences

    return PlannedSchedule(
        workflow_file=wf_path.name,
        cron_expressions=cron_exprs,
        planned_posts_per_week=weekly_total if (cron_exprs and all_estimated) else None,
    )


def load_all_planned_schedules(brand_ids, workflows_dir: Path) -> Dict[str, Optional[PlannedSchedule]]:
    return {brand_id: load_planned_schedule(brand_id, workflows_dir) for brand_id in brand_ids}
