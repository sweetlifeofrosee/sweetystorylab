"""
scripts/report/render_report.py

Renders a WeeklyReport (aggregate.py) into the Markdown structure
frozen in the Architecture and Development Guide §14.4: Summary,
Operational Health, Editorial Intelligence, Audience & Engagement,
Trends, Data Notes.

V1 notes rendered inline, deliberately, rather than silently omitted:
  - Audience & Engagement always renders as unavailable (no platform
    source implemented yet).
  - Trends renders as "not enough history yet" until this report has
    run for a few weeks (V1 has no prior-week data to compare against).
  - Any per-brand data gap surfaces in that brand's Data Notes.
"""
from typing import List

from .aggregate import WeeklyReport, BrandWeeklyReport


def _fmt_int(value) -> str:
    return str(value) if value is not None else "unavailable"


def _render_summary(report: WeeklyReport) -> List[str]:
    lines = ["## Summary", ""]
    lines.append("| Brand | Score | Basis | Subjects this week |")
    lines.append("|---|---|---|---|")
    for b in report.brands:
        score_str = f"{b.score.value}" if b.score.value is not None else "n/a"
        subjects_str = str(len(b.editorial.subjects_covered_this_week))
        lines.append(f"| {b.brand_emoji} {b.brand_name} | {score_str} | {b.score.basis} | {subjects_str} |")
    lines.append("")
    if any(b.score.degraded for b in report.brands):
        lines.append(
            "_All scores this week are operational-only: Audience/Engagement data is "
            "unavailable in V1 (see §14.6 of the Architecture and Development Guide)._"
        )
        lines.append("")
    return lines


def _render_operational_health(report: WeeklyReport) -> List[str]:
    lines = ["## Operational Health", ""]
    for b in report.brands:
        op = b.operational
        lines.append(f"### {b.brand_emoji} {b.brand_name}")
        lines.append("")
        lines.append(f"- **Planned posts this week:** {_fmt_int(op.planned_posts_per_week)}"
                      + (f" (from `{op.schedule_workflow_file}`)" if op.schedule_workflow_file else ""))
        lines.append(f"- **Actual posts this week:** {_fmt_int(op.actual_posts_this_week)}")
        lines.append(f"- _{op.actual_source_note}_")
        lines.append("")
    return lines


def _render_editorial_intelligence(report: WeeklyReport) -> List[str]:
    lines = ["## Editorial Intelligence", ""]
    for b in report.brands:
        ed = b.editorial
        lines.append(f"### {b.brand_emoji} {b.brand_name}")
        lines.append("")
        if ed.subjects_covered_this_week:
            lines.append("**Subjects covered this week:**")
            for s in ed.subjects_covered_this_week:
                lines.append(f"- {s}")
        else:
            lines.append("**Subjects covered this week:** none recorded.")
        lines.append("")
        lines.append(
            f"**Cumulative subjects tracked (all-time):** {_fmt_int(ed.cumulative_subjects_count)}"
        )
        lines.append("")
        lines.append(
            "**Best-performing categories / themes / top hooks / category frequency:** "
            "not yet available -- no brand currently captures category, theme, or hook "
            "metadata (Guide §7, §12). This section will populate once that schema work "
            "lands; it is left visible here rather than omitted, so the report's shape "
            "doesn't need to change when it does."
        )
        lines.append("")
    return lines


def _render_audience_engagement(report: WeeklyReport) -> List[str]:
    lines = ["## Audience & Engagement", ""]
    lines.append(
        "_Unavailable in V1. The platform-data adapter interface is scaffolded "
        "(`scripts/report/platform_source/`), but no source is implemented yet -- "
        "enrichment is deferred to V2 per the approved architecture (Guide §14.3)._"
    )
    lines.append("")
    return lines


def _render_trends(report: WeeklyReport) -> List[str]:
    lines = ["## Trends", ""]
    lines.append(
        "_Not enough history yet. This section will show a 4-week rolling view once "
        "this report has run for a few weeks._"
    )
    lines.append("")
    return lines


def _render_data_notes(report: WeeklyReport) -> List[str]:
    lines = ["## Data Notes", ""]
    any_notes = False
    for b in report.brands:
        for note in b.data_notes:
            lines.append(f"- **{b.brand_name}:** {note}")
            any_notes = True
    if not any_notes:
        lines.append("- No data gaps this week.")
    lines.append("")
    return lines


def render_markdown(report: WeeklyReport) -> str:
    week_label = f"{report.week_start.date().isoformat()} to {report.week_end.date().isoformat()}"
    lines = [f"# Weekly Performance Report — Week of {week_label}", ""]
    lines += _render_summary(report)
    lines += _render_operational_health(report)
    lines += _render_editorial_intelligence(report)
    lines += _render_audience_engagement(report)
    lines += _render_trends(report)
    lines += _render_data_notes(report)
    return "\n".join(lines).rstrip() + "\n"
