"""
scripts/report/platform_source/csv_source.py

V1 stub. Deliberately unimplemented, per the approved v1.3 architecture
(Guide §14.3, §14.6): "use exported platform CSVs... for the first
implementation... I want to validate the reporting architecture first,
then swap the data source later without changing the aggregation or
rendering layers."

The real column mapping is blocked on an open item from the design
(Guide §14.6): a sample of the Meta CSV export's actual column headers.
Rather than guess a mapping and risk silently misreading real data,
get_metrics() always returns None -- the report runs fully in its
repository-first, operational-only mode until this is implemented.

To implement V2's real mapping:
  1. Set `export_path` to wherever the weekly CSV export actually lands
     (Guide §14.6, open item #3 -- manual drop vs. an existing process).
  2. Parse the CSV, map its columns onto PostMetrics/BrandWeekMetrics
     (see base.py) -- most likely via each row's brand identifier and
     a publish-date or story_id column.
  3. Nothing outside this file needs to change: aggregate.py and
     render_report.py already treat get_metrics() returning real data
     the same way they treat it returning None today, via the
     PlatformSource interface.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import PlatformSource, BrandWeekMetrics


class CSVPlatformSource(PlatformSource):
    def __init__(self, export_path: Optional[Path] = None):
        # Not read from anywhere yet -- accepted now so V2 doesn't need
        # to change this class's constructor signature or call sites,
        # only get_metrics()'s body.
        self.export_path = export_path

    def get_metrics(
        self, brand_id: str, week_start: datetime, week_end: datetime
    ) -> Optional[BrandWeekMetrics]:
        # V1: intentionally not implemented. See module docstring.
        return None
