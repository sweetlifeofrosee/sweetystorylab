"""
tests/report/test_aggregate.py

Covers the honesty guarantee at the center of aggregate.py: a score is
only ever produced from data that actually exists, and the module must
never fabricate a placeholder number when it doesn't.
"""
from scripts.report.aggregate import (
    OperationalHealth,
    _compute_score,
)


def _op(planned=None, actual=None):
    return OperationalHealth(
        planned_posts_per_week=planned,
        actual_posts_this_week=actual,
        actual_source_note="test note",
        schedule_workflow_file="test.yml",
    )


def test_score_is_none_when_actual_data_unavailable():
    # Horror Lab's real-world case: no repo-side signal at all.
    score = _compute_score(_op(planned=7, actual=None), platform=None)
    assert score.value is None
    assert score.degraded is True
    assert "insufficient" in score.basis.lower() or "insufficient" in score.basis


def test_score_is_none_when_planned_data_unavailable():
    score = _compute_score(_op(planned=None, actual=3), platform=None)
    assert score.value is None
    assert score.degraded is True


def test_score_is_none_when_planned_is_zero():
    # Avoid a division-by-zero path producing a misleading result --
    # zero planned posts is "couldn't determine a cadence," not "100%
    # of nothing."
    score = _compute_score(_op(planned=0, actual=0), platform=None)
    assert score.value is None


def test_score_computed_as_percentage_of_planned():
    score = _compute_score(_op(planned=7, actual=1), platform=None)
    assert score.value == round(1 / 7 * 100, 1)
    assert score.degraded is True


def test_score_is_capped_at_100_even_if_actual_exceeds_planned():
    # e.g. a manual workflow_dispatch run on top of the normal cron
    # shouldn't produce a score above 100.
    score = _compute_score(_op(planned=7, actual=10), platform=None)
    assert score.value == 100.0


def test_score_is_zero_when_no_posts_landed(tmp_path=None):
    score = _compute_score(_op(planned=7, actual=0), platform=None)
    assert score.value == 0.0
    assert score.degraded is True


def test_score_always_degraded_in_v1():
    # No platform source is implemented in V1 -- every score, even a
    # fully-computable operational one, must be marked degraded so
    # rendering can label it "operational-only" rather than implying a
    # complete Audience/Engagement/Operational blend.
    score = _compute_score(_op(planned=7, actual=7), platform=None)
    assert score.degraded is True
