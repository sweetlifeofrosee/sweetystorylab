"""
scripts/report/platform_source/base.py

The adapter interface referenced throughout the approved v1.3 design
(Guide §14.3). aggregate.py and render_report.py depend only on this
interface and on the normalized dict shape documented below -- never
on a concrete source -- so V2 can add a real CSV mapping or a live
Graph API source without any change to scoring or rendering logic.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, TypedDict, List


class PostMetrics(TypedDict, total=False):
    """Per-post platform metrics, when a source can provide them."""
    story_id: Optional[str]      # preferred join key, per Guide §14.3 -- optional,
                                   # falls back to brand + publish_date when absent
    publish_date: Optional[str]   # ISO date string, used as the fallback join key
    views: int
    watch_time_seconds: float
    likes: int
    comments: int
    shares: int
    retention_pct: float


class BrandWeekMetrics(TypedDict, total=False):
    """
    Normalized shape returned by get_metrics(). All keys are optional --
    a source only fills in what it actually has. aggregate.py treats
    any missing key as "unknown," not as zero.
    """
    follower_delta: int
    posts: List[PostMetrics]


class PlatformSource(ABC):
    """
    Every platform-data source (CSV export today, a future live API)
    implements this same interface. See Guide §14.3 for the full
    rationale.
    """

    @abstractmethod
    def get_metrics(
        self, brand_id: str, week_start: datetime, week_end: datetime
    ) -> Optional[BrandWeekMetrics]:
        """
        Returns normalized platform metrics for `brand_id` within
        [week_start, week_end), or None if unavailable for this
        brand/week (missing export, brand not present in the export,
        source unreachable, etc.). Returning None is a normal,
        expected outcome this interface is built around -- callers
        must treat it as "no enrichment this week," not as an error.
        """
        raise NotImplementedError
