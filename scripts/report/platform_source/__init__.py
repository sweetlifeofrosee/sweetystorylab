"""
scripts/report/platform_source/

Platform-data adapter interface (Guide §14.3). Scaffolded in V1, not
implemented: get_active_source() below returns a source whose
get_metrics() always returns None, so the report runs in its
repository-first, operational-only mode until a real source lands.

V2 will add csv_source.py's real CSV column mapping and/or
graph_api_source.py, and this factory becomes the single place that
changes to point at it -- aggregate.py and render_report.py are
written against PlatformSource's interface only and do not need to
change.
"""
from .base import PlatformSource
from .csv_source import CSVPlatformSource


def get_active_source() -> PlatformSource:
    """
    The single swap point described in Guide §14.3. V1 always returns
    the CSV adapter, which is itself an unimplemented stub (see
    csv_source.py) until a sample export's column headers are
    available (Guide §14.6, open item #2). Swapping to a live Graph
    API source in V2 means changing this one line, not touching
    aggregate.py or render_report.py.
    """
    return CSVPlatformSource()
