"""
scripts/report/

Weekly Performance Report -- SweetyStoryLab v1.3, first Operations &
Analytics-phase feature.

Version 1 scope (per the approved v1.3 architecture, Architecture and
Development Guide §14):
  - Repository-first: the report is fully buildable from repo-side
    data alone. Nothing here requires network access or credentials.
  - Focuses on Operational Health and Editorial Intelligence.
  - The platform-data adapter interface (platform_source/) is scaffolded
    so a future version can plug in a CSV export or a live Graph API
    source without changing aggregate.py or render_report.py -- but no
    enrichment source is implemented yet, so Audience & Engagement
    always renders as unavailable in V1.

This package is entirely additive and read-only with respect to the
generation/posting pipeline: it imports core.config.loader (read-only)
to discover brands, and never imports or calls anything under
core.story, core.providers, core.video, or core.pipeline.run/cli.
It never writes to any file the generation or posting workflows read
from (core principle: "descriptive, not prescriptive" -- see the
Architecture and Development Guide §11, §14.2).
"""
