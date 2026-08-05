# Weekly Performance Report — Feature Design
**SweetyStoryLab v1.3 — Operations & Analytics Phase, Feature 1**
**Status: Finalized — ready for implementation**

## 1. Goal & Non-Goals

**Goal:** Produce a weekly Markdown report summarizing how Horror Lab and Mystery Lab (and any future brands) performed, combining platform metrics with repo-side editorial signals into a single cross-brand view.

**Architecture stance: repository-first.** The repo-side editorial history is the source of truth the report can always build from. Platform metrics are a supplementary enrichment layer — valuable when present, never a dependency. The report generates every week regardless of whether any platform data source is reachable.

**Non-goals (explicitly out of scope):**
- No changes to prompts, generation logic, or posting behavior.
- No changes to the existing production workflows for Horror Lab / Mystery Lab.
- Read-only with respect to content pipelines — this feature only *reads* data they already produce and *writes* a report.

**Design principle: descriptive, not prescriptive.** The Weekly Performance Report summarizes historical performance. It does not influence generation, prompts, scheduling, or topic selection, and nothing in this pipeline writes back to any file the generation or posting pipelines read from. If AI-assisted recommendations are built later, they consume this reporting layer as an input — they do not modify it, and this layer never becomes a control surface for the content pipeline.

## 2. Data Sources

| Source | Role | What it provides | Access method | Required? |
|---|---|---|---|---|
| Repo-side editorial history (Mystery Lab's persisted history, Horror Lab equivalent) | **Primary — source of truth** | Posting consistency, story themes/tags/categories, hooks, generation errors or skips, publish timestamps | Direct read from repo JSON/log files | Yes |
| Platform data (v1: exported CSVs, e.g. the Meta export already in use) | Supplementary enrichment | Views, watch time, likes, comments, shares, retention, follower delta | Manually-dropped or committed CSV files, read from a fixed `data/exports/` path | No — optional |

Both sources are read into a common weekly window (Mon–Sun, or your preferred boundary) and joined by brand + publish date. If no platform export is present for a given week, the report still builds in full from repo data, with platform-dependent sections clearly marked as unavailable rather than guessed at or omitted silently.

### Recommended field: `story_id`

**For future compatibility, not required for v1 implementation.** Joining repo editorial history to platform analytics by brand + publish date works for the current one-post-per-day model, but breaks down as soon as any of the following becomes true: multiple posts per day, reposts, retries after a failed publish, or analytics from additional platforms with their own timestamps.

The reporting model should therefore reserve a lightweight `story_id` field — a stable, unique identifier assigned per published story — as the preferred join key wherever it's available, with brand + publish date remaining as the fallback join for data that predates or lacks it. This is purely a recommendation for the reporting model's schema going forward:

- **No production pipeline change required now.** Horror Lab and Mystery Lab keep generating and publishing exactly as they do today.
- **When/if a `story_id` is introduced upstream** (e.g., the editorial history gains an id field, or a platform export includes a matching reference), the aggregation layer should prefer it automatically — join on `story_id` when present on both sides, fall back to brand + publish date otherwise. No redesign needed, just a join-key preference.
- **Format is intentionally unspecified here** — whatever's cheapest to generate where stories are currently created (e.g. a hash, a timestamp-based slug, a UUID) is fine; the reporting model only needs *a* stable identifier to exist, not a particular scheme.

This keeps today's architecture untouched while leaving a clear, low-friction path to more precise joins later.

### Data source abstraction (for the later API swap)

To let you validate the architecture on CSVs now and swap to live Graph API pulls later *without touching aggregation or rendering*, platform data is accessed only through a small adapter interface:

```
scripts/report/platform_source/
  base.py          # defines get_metrics(brand, week) -> normalized dict, or None if unavailable
  csv_source.py     # v1: reads the Meta-style CSV export, maps columns to the normalized schema
  graph_api_source.py  # v2 (future, not built yet): same interface, calls Graph API instead
```

`aggregate.py` and `render_report.py` only ever talk to the normalized dict shape returned by `get_metrics()` — they don't know or care whether it came from a CSV or an API. Swapping sources later is a one-line change (which adapter gets instantiated), with no changes to scoring or rendering logic. The normalized dict should include an optional `story_id` field alongside brand/date, so the join-key preference described below (`story_id` when available, brand + publish date as fallback) works identically regardless of which adapter is in use.

## 3. Architecture

A **new, isolated GitHub Actions workflow** — does not touch the existing daily posting workflows.

```
.github/workflows/weekly-report.yml   (new — cron, e.g. Monday 06:00 UTC)
  → scripts/report/load_editorial_history.py   (reads repo-side logs/history — always runs)
  → scripts/report/platform_source/csv_source.py  (reads CSV export if present — optional)
  → scripts/report/aggregate.py                (joins + computes composite scores)
  → scripts/report/render_report.py            (renders Markdown from template)
  → commits reports/weekly/YYYY-Www.md to the repo
```

Design principles:
- **Repository-first** — editorial history load happens unconditionally and first; the report is fully buildable from it alone. Platform data is layered on top, never a precondition.
- **Fail-soft per source** — if the platform export is missing, stale, or malformed, the report still generates with a "data unavailable" note for that section rather than failing the whole run.
- **Source-agnostic aggregation** — no changes needed to `aggregate.py` or `render_report.py` when the platform source later moves from CSV to live API (see §2 adapter interface).
- **No shared state with generation** — this workflow never writes to any file the generation/posting pipelines read from, and (for v1) needs no new API credentials at all.
- **Descriptive, not prescriptive** — the workflow only writes the report file; it has no code path that touches prompts, scheduling config, or topic selection, now or in any planned future version.

## 4. Metrics Model: Weighted Composite

Since you want "all of the above, weighted summary," each brand gets a **Weekly Performance Score** built from three pillars:

| Pillar | Example metrics | Suggested default weight |
|---|---|---|
| Audience | Views, watch time, follower delta | 40% |
| Engagement | Likes, comments, shares, retention % | 40% |
| Operational Health | Posting consistency (planned vs. actual), pipeline run status, generation/publishing errors | 20% |

Each pillar is normalized to a 0–100 scale (e.g., relative to that brand's trailing 4-week average) before weighting, so brands of different sizes stay comparable to *themselves* over time, and a cross-brand comparison is expressed as relative movement, not raw scale.

Weights live in a small config file (`scripts/report/weights.yaml`) so you can retune them later without touching code.

**Degraded mode:** if platform data is unavailable for a brand that week, the Audience and Engagement pillars are omitted from that brand's score (not zeroed — zeroing would misrepresent a data gap as poor performance), and the composite score is computed from Operational Health alone, clearly labeled as "operational-only score, platform data unavailable this week."

## 5. Report Structure (Markdown output)

```
# Weekly Performance Report — Week of {date}

## Summary
- Cross-brand table: score, WoW change, top metric mover per brand
- Note if any brand's score is operational-only this week (platform data unavailable)

## Operational Health
### Horror Lab
- Posting consistency (planned vs. actual), pipeline run status
- Generation/publishing errors or skips
### Mystery Lab
- (same structure)

## Editorial Intelligence
### Horror Lab
- Best-performing categories, best-performing themes, top hooks
- Category frequency, subjects covered
- Editorial observations
### Mystery Lab
- (same structure)

## Audience & Engagement
### Horror Lab
- Views, watch time, follower delta, likes, comments, shares, retention
- Notable posts (best & worst performing), when platform data present
### Mystery Lab
- (same structure)

## Trends
- 4-week rolling chart data (as a table, or Mermaid chart block)

## Data Notes
- Any sources that failed to fetch this week, flagged explicitly
```

**Operational Health** and **Editorial Intelligence** are deliberately separate top-level sections rather than a merged "insights" block — one tells you whether the pipeline ran cleanly, the other tells you what the content actually was and how it's trending. Keeping them apart means a bad week operationally (a missed post) never gets visually blended with or mistaken for a bad week editorially (a weak-performing theme), and vice versa.

### Editorial Intelligence — content detail

Derived entirely from repo-side editorial history, so always available regardless of platform data status. Per brand, per week:

- **Best-performing categories** — which story categories this week's top posts belonged to (requires posts to be joined against platform metrics when available; falls back to "most-produced categories" when platform data is absent)
- **Best-performing themes** — same idea, one level more granular than category
- **Top hooks** — the opening lines/hooks used, ranked by performance where available, otherwise surfaced as a representative sample for editorial review
- **Category frequency** — distribution of categories produced this week (and how it compares to the trailing 4-week distribution — is the brand drifting toward or away from certain categories?)
- **Subjects covered** — the specific topics/subjects touched on, so you can spot repetition or gaps at a glance
- **Editorial observations** — a short freeform notes block (e.g., "3 of 7 posts this week used a question-based hook," "Category X hasn't appeared in 3 weeks") — pattern-level observations generated from the aggregation step, not a generic template

### Operational Health — pipeline detail

Also derived entirely from repo-side data, always available:

- **Posting consistency** — planned vs. actual posts this week, gaps or skips
- **Pipeline health** — whether scheduled generation/publishing runs completed, partial-failure counts
- **Generation/publishing errors** — errors surfaced from the automation logs, counted and summarized (not full stack traces — this is a summary report, not a debug log)

This split keeps the report usable purely as an operations dashboard, purely as a content-intelligence briefing, or as both — without either one depending on the other.

## 6. Delivery

- Rendered Markdown committed to `reports/weekly/YYYY-Www.md`.
- Optionally, a `reports/weekly/latest.md` symlink/copy for easy reference.
- (Future-friendly: this structure makes it trivial to *also* email/Slack it later without redesigning — the render step just gets a second output target.)

## 7. Open Decisions Before Build

1. **Where exactly** does Mystery Lab's persisted editorial history live in the repo (path/format — JSON structure, field names for category/theme/hook/subject), and does Horror Lab have an equivalent, or does it need one added (read-only addition, not a pipeline change)?
2. **The Meta CSV export** — can you share (or point me to) a sample of its column headers, so `csv_source.py`'s column mapping is built against the real format rather than assumed?
3. **Where the CSV lands** — do you manually drop it into a repo folder each week, or is there already a process for that? This determines whether `csv_source.py` just needs a fixed read path or also needs to handle "file not present yet."
4. **Week boundary & timezone** for the report window?

Once you confirm those, I can scaffold the actual workflow file, scripts, and a sample rendered report — repo-first, CSV-backed, with Operational Health and Editorial Intelligence as the two anchor sections.
