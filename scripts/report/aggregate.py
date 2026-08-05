"""
scripts/report/aggregate.py

Combines editorial_history.py, schedule.py, and a PlatformSource into
the per-brand data model render_report.py renders. This is the one
module that computes the Weekly Performance Score (Guide §14.4).

V1 honesty rule: a score is only ever produced from data that actually
exists. If there isn't enough to compute a meaningful number, this
module returns score=None with a stated reason -- it never fabricates
a placeholder score. Given the real data gaps this codebase currently
has (Guide §7, §12), that will be the common case in V1: Audience and
Engagement are always unavailable (no platform source implemented
yet), and Operational Health itself is only partially available (a
commit-count proxy for Mystery Lab; nothing at all for Horror Lab).
This is a deliberate, documented consequence of the repository-first
principle -- not a bug to paper over before shipping V1.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .editorial_history import EditorialHistory, load_editorial_history
from .platform_source.base import PlatformSource, BrandWeekMetrics
from .schedule import PlannedSchedule, load_planned_schedule


@dataclass
class OperationalHealth:
    planned_posts_per_week: Optional[int]
    actual_posts_this_week: Optional[int]  # None if no repo-side signal exists
    actual_source_note: Optional[str]  # explains what actual_posts_this_week measures, or why it's None
    schedule_workflow_file: Optional[str]


@dataclass
class EditorialIntelligence:
    subjects_covered_this_week: List[str]
    cumulative_subjects_count: Optional[int]
    # No data source yet anywhere in the repo (Guide §7, §12) -- always
    # empty in V1. Rendered explicitly as "not yet captured," not omitted.
    best_categories: List[str] = field(default_factory=list)
    best_themes: List[str] = field(default_factory=list)
    top_hooks: List[str] = field(default_factory=list)
    category_frequency: Dict[str, int] = field(default_factory=dict)
    observations: List[str] = field(default_factory=list)


@dataclass
class CompositeScore:
    value: Optional[float]  # None if there isn't enough data to compute one
    basis: str  # human-readable description of what the score is/isn't based on
    degraded: bool  # True whenever Audience/Engagement are missing (always True in V1)


@dataclass
class BrandWeeklyReport:
    brand_id: str
    brand_name: str
    brand_emoji: str
    operational: OperationalHealth
    editorial: EditorialIntelligence
    platform: Optional[BrandWeekMetrics]
    score: CompositeScore
    data_notes: List[str] = field(default_factory=list)


@dataclass
class WeeklyReport:
    week_start: datetime
    week_end: datetime
    brands: List[BrandWeeklyReport]


def _build_editorial_intelligence(history: EditorialHistory) -> EditorialIntelligence:
    return EditorialIntelligence(
        subjects_covered_this_week=history.weekly_new_subjects,
        cumulative_subjects_count=history.cumulative_subjects_count,
        best_categories=history.weekly_categories,
        best_themes=history.weekly_themes,
        top_hooks=history.weekly_hooks,
        category_frequency={},
        observations=[],
    )


def _build_operational_health(
    history: EditorialHistory, planned: Optional[PlannedSchedule]
) -> OperationalHealth:
    planned_count = planned.planned_posts_per_week if planned else None
    workflow_file = planned.workflow_file if planned else None

    if history.available:
        actual = history.weekly_commit_count
        note = (
            "Derived from commits to used_subjects.json this week (one commit per "
            "accepted, non-duplicate story -- see editorial_history.py). This is a "
            "proxy for successful posts, not a verified count: it won't reflect a "
            "run that failed before generation, and it undercounts if a brand ever "
            "accepts a repeat subject without a file change."
        )
    else:
        actual = None
        note = (
            "No repository-side signal exists for this brand's actual post outcomes "
            "(no dedup file to derive commit history from). The per-post operational "
            "log this pipeline produces is artifact-only with 30-day retention, not "
            "committed to the repo -- see Guide §7 and §12."
        )

    return OperationalHealth(
        planned_posts_per_week=planned_count,
        actual_posts_this_week=actual,
        actual_source_note=note,
        schedule_workflow_file=workflow_file,
    )


def _compute_score(
    operational: OperationalHealth, platform: Optional[BrandWeekMetrics]
) -> CompositeScore:
    # Per Guide §14.4's weighting model: Audience 40%, Engagement 40%,
    # Operational Health 20%. V1 never has Audience/Engagement (no
    # platform source implemented), so composite scoring is always in
    # degraded mode. It is only actually computable when Operational
    # Health itself has real data.
    if platform is not None:
        # Would only happen once a real PlatformSource is wired in
        # (V2). Left unimplemented deliberately: scoring logic for
        # Audience/Engagement pillars is out of scope for this V1
        # repository-first pass and shouldn't be guessed at here.
        pass

    if operational.actual_posts_this_week is None or operational.planned_posts_per_week is None:
        return CompositeScore(
            value=None,
            basis="Insufficient repository-side data to compute even an operational-only score this week.",
            degraded=True,
        )

    if operational.planned_posts_per_week == 0:
        return CompositeScore(
            value=None,
            basis="Planned posting cadence could not be determined from this brand's workflow.",
            degraded=True,
        )

    consistency_ratio = min(
        operational.actual_posts_this_week / operational.planned_posts_per_week, 1.0
    )
    return CompositeScore(
        value=round(consistency_ratio * 100, 1),
        basis=(
            "Operational-only score (Audience/Engagement unavailable -- no platform "
            "source implemented in V1): actual vs. planned posts this week, as a "
            "percentage, capped at 100."
        ),
        degraded=True,
    )


def build_brand_report(
    brand_id: str,
    brand_name: str,
    brand_emoji: str,
    brand_dir: Path,
    repo_root: Path,
    workflows_dir: Path,
    week_start: datetime,
    week_end: datetime,
    platform_source: PlatformSource,
) -> BrandWeeklyReport:
    history = load_editorial_history(brand_id, brand_dir, repo_root, week_start, week_end)
    planned = load_planned_schedule(brand_id, workflows_dir)
    platform = platform_source.get_metrics(brand_id, week_start, week_end)

    operational = _build_operational_health(history, planned)
    editorial = _build_editorial_intelligence(history)
    score = _compute_score(operational, platform)

    data_notes = []
    if not history.available:
        data_notes.append(f"Editorial history: {history.unavailable_reason}")
    if planned is None:
        data_notes.append(
            "Planned posting cadence: no workflow file found referencing "
            f"--brand {brand_id}; could not determine a schedule."
        )
    if platform is None:
        data_notes.append(
            "Audience & Engagement: no platform data source is implemented in V1 "
            "(platform_source scaffolded per Guide §14.3, enrichment deferred to V2)."
        )

    return BrandWeeklyReport(
        brand_id=brand_id,
        brand_name=brand_name,
        brand_emoji=brand_emoji,
        operational=operational,
        editorial=editorial,
        platform=platform,
        score=score,
        data_notes=data_notes,
    )
