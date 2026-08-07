# Weekly Performance Report — Week of 2026-07-29 to 2026-08-05

## Summary

| Brand | Score | Basis | Subjects this week |
|---|---|---|---|
| 👻 Horror Lab | n/a | Insufficient repository-side data to compute even an operational-only score this week. | 0 |
| 📜 Mystery Lab | 100.0 | Operational-only score (Audience/Engagement unavailable -- no platform source implemented in V1): actual vs. planned posts this week, as a percentage, capped at 100. | 9 |

_All scores this week are operational-only: Audience/Engagement data is unavailable in V1 (see §14.6 of the Architecture and Development Guide)._

## Operational Health

### 👻 Horror Lab

- **Planned posts this week:** 7 (from `post.yml`)
- **Actual posts this week:** unavailable
- _No repository-side signal exists for this brand's actual post outcomes (no dedup file to derive commit history from). The per-post operational log this pipeline produces is artifact-only with 30-day retention, not committed to the repo -- see Guide §7 and §12._

### 📜 Mystery Lab

- **Planned posts this week:** 7 (from `post_mystery.yml`)
- **Actual posts this week:** 10
- _Derived from commits to used_subjects.json this week (one commit per accepted, non-duplicate story -- see editorial_history.py). This is a proxy for successful posts, not a verified count: it won't reflect a run that failed before generation, and it undercounts if a brand ever accepts a repeat subject without a file change._

## Editorial Intelligence

### 👻 Horror Lab

**Subjects covered this week:** none recorded.

**Cumulative subjects tracked (all-time):** unavailable

**Best-performing categories / themes / top hooks / category frequency:** not yet available -- no brand currently captures category, theme, or hook metadata (Guide §7, §12). This section will populate once that schema work lands; it is left visible here rather than omitted, so the report's shape doesn't need to change when it does.

### 📜 Mystery Lab

**Subjects covered this week:**
- Dogon Tribe
- Indus Valley
- Indus Valley Civilization
- Moche Temples
- Nubian Pyramids
- Rapa Nui Moai
- Tanis
- Terracotta Army
- Thonis-Heraklion

**Cumulative subjects tracked (all-time):** 8

**Best-performing categories / themes / top hooks / category frequency:** not yet available -- no brand currently captures category, theme, or hook metadata (Guide §7, §12). This section will populate once that schema work lands; it is left visible here rather than omitted, so the report's shape doesn't need to change when it does.

## Audience & Engagement

_Unavailable in V1. The platform-data adapter interface is scaffolded (`scripts/report/platform_source/`), but no source is implemented yet -- enrichment is deferred to V2 per the approved architecture (Guide §14.3)._

## Trends

_Not enough history yet. This section will show a 4-week rolling view once this report has run for a few weeks._

## Data Notes

- **Horror Lab:** Editorial history: No used_subjects.json found for this brand. This brand has no repository-side editorial memory yet (no dedup module configured -- see Guide §7's content.dedup_module field).
- **Horror Lab:** Audience & Engagement: no platform data source is implemented in V1 (platform_source scaffolded per Guide §14.3, enrichment deferred to V2).
- **Mystery Lab:** Audience & Engagement: no platform data source is implemented in V1 (platform_source scaffolded per Guide §14.3, enrichment deferred to V2).
