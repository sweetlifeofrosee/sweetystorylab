"""
scripts/report/run_weekly_report.py

Entrypoint for the Weekly Performance Report. Discovers brands the
same way the rest of the platform does (reads brands/*/config.yaml via
core.config.loader -- read-only, no import of core.story, core.providers,
core.video, or core.pipeline.run/cli), builds each brand's report, and
writes the rendered Markdown to reports/weekly/.

Usage (from repo root):
    python -m scripts.report.run_weekly_report
    python -m scripts.report.run_weekly_report --week-start 2026-07-27

This module never touches anything the generation/posting pipeline
reads from -- see scripts/report/__init__.py for the full statement of
that boundary.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import sys

# Allow running as `python -m scripts.report.run_weekly_report` from
# the repo root without requiring the package to be installed.
_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

from core.config.loader import load_brand_config, ConfigError  # noqa: E402

from .aggregate import build_brand_report, WeeklyReport  # noqa: E402
from .platform_source import get_active_source  # noqa: E402
from .render_report import render_markdown  # noqa: E402


def discover_brands(brands_root: Path):
    """
    Mirrors how the rest of the platform discovers brands: any
    directory under brands/ with a config.yaml is a brand. Generic by
    design -- adding a third brand requires no change here.
    """
    brands = []
    print(f"[weekly-report] Discovering brands under: {brands_root.resolve()}", file=sys.stderr)
    if not brands_root.exists():
        print(f"[weekly-report] WARNING: {brands_root.resolve()} does not exist.", file=sys.stderr)
        return brands
    for entry in sorted(brands_root.iterdir()):
        if not entry.is_dir():
            continue
        config_path = entry / "config.yaml"
        if not config_path.exists():
            continue
        try:
            config = load_brand_config(entry)
        except ConfigError as exc:
            print(f"WARNING: skipping {entry.name}: {exc}", file=sys.stderr)
            continue
        subjects_path = entry / "used_subjects.json"
        print(
            f"[weekly-report] Found brand '{config.id}' at {entry.resolve()} "
            f"(used_subjects.json exists: {subjects_path.exists()}"
            + (f", size: {subjects_path.stat().st_size} bytes)" if subjects_path.exists() else ")"),
            file=sys.stderr,
        )
        brands.append(config)
    return brands


def build_weekly_report(
    repo_root: Path, week_start: datetime, week_end: datetime
) -> WeeklyReport:
    brands_root = repo_root / "brands"
    workflows_dir = repo_root / ".github" / "workflows"
    platform_source = get_active_source()

    brand_configs = discover_brands(brands_root)
    if not brand_configs:
        print(f"WARNING: no brands discovered under {brands_root}", file=sys.stderr)

    brand_reports = [
        build_brand_report(
            brand_id=cfg.id,
            brand_name=cfg.name,
            brand_emoji=cfg.emoji,
            brand_dir=cfg.brand_dir,
            repo_root=repo_root,
            workflows_dir=workflows_dir,
            week_start=week_start,
            week_end=week_end,
            platform_source=platform_source,
        )
        for cfg in brand_configs
    ]

    return WeeklyReport(week_start=week_start, week_end=week_end, brands=brand_reports)


def _default_week_window() -> tuple:
    """
    Default: the 7 days ending now (UTC). The exact calendar boundary
    and timezone convention is an open item in the approved design
    (Guide §14.6) -- this rolling-7-day default is a reasonable,
    unambiguous placeholder until that's settled, and is fully
    overridable via --week-start / --week-end.
    """
    now = datetime.now(timezone.utc)
    return now - timedelta(days=7), now


def main():
    parser = argparse.ArgumentParser(description="Generate the SweetyStoryLab Weekly Performance Report.")
    parser.add_argument("--repo-root", default=".", help="Path to the repository root (default: cwd).")
    parser.add_argument("--week-start", default=None, help="ISO date/datetime for the window start (default: 7 days ago, UTC).")
    parser.add_argument("--week-end", default=None, help="ISO date/datetime for the window end (default: now, UTC).")
    parser.add_argument("--output-dir", default="reports/weekly", help="Where to write the rendered report, relative to repo root.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    default_start, default_end = _default_week_window()
    week_start = datetime.fromisoformat(args.week_start) if args.week_start else default_start
    week_end = datetime.fromisoformat(args.week_end) if args.week_end else default_end
    if week_start.tzinfo is None:
        week_start = week_start.replace(tzinfo=timezone.utc)
    if week_end.tzinfo is None:
        week_end = week_end.replace(tzinfo=timezone.utc)

    report = build_weekly_report(repo_root, week_start, week_end)
    markdown = render_markdown(report)

    output_dir = repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    iso_year, iso_week, _ = week_end.isocalendar()
    filename = f"{iso_year}-W{iso_week:02d}.md"
    output_path = output_dir / filename
    output_path.write_text(markdown, encoding="utf-8")

    latest_path = output_dir / "latest.md"
    latest_path.write_text(markdown, encoding="utf-8")

    print(f"Wrote {output_path}")
    print(f"Wrote {latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
