# Architecture

## The shape

```
                                  GitHub Actions runner (ubuntu, fresh VM each run)
                     ┌──────────────────────────────────────────────────────────────┐
  Open-Meteo API ──▶ │                                                              │
  news.ycombinator ─▶│  pixi run scrape ──▶ data/raw, data/tidy, data/runs.jsonl   │──git push──▶ repo main
  api.github.com ───▶│                          │                                   │
                     │                   pixi run build ──▶ site/data/*.json         │
                     │                          │                                   │
                     │                   upload site/ ──▶ actions/deploy-pages       │──────────▶ Pages CDN
                     └──────────────────────────────────────────────────────────────┘
                                                                                        browser ──fetch──▶ site/data/*.json
```

Three processes, three storage tiers, one static site. Every arrow is a plain
file or a plain HTTP call; there is no daemon, queue, or database anywhere.

## Decisions and their reasons

**Sources are classes with `fetch()` and `parse()` and nothing else.**
`parse` is a pure function of bytes, so it is testable from a fixture file
with no network. `fetch` is the only place a source touches the internet.
The pipeline, not the source, decides where bytes go. This is the separation
that lets you re-parse history after a parser fix.

**Raw snapshots are committed.** They cost a few tens of kilobytes per run
(the HN page is the largest at ~35 KB) and they are the only way to recover
from a parser bug. At four runs a day that is under 50 MB a year, which git
handles without complaint. If a source grew to megabytes per run, the right
move is a compressed snapshot (`.json.gz`) or an object store, not dropping
the tier.

**Tidy tables are CSV, not Parquet.** CSV diffs are readable in a pull
request and on github.com; Parquet is opaque binary. At this size the
performance difference is nil. Switch when a table passes a few hundred
thousand rows, and do it in `pipeline.py` alone: the sources and the site
never touch the tidy files directly.

**The site reads JSON, not the CSVs.** `build` trims history (HN ships 30
days), reshapes for the browser, and writes a manifest with counts and
timestamps. This keeps the page fast and keeps the browser ignorant of the
storage format.

**Colour and identity.** Each city and each repo gets a fixed colour on first
sight (alphabetical) and keeps it across filters, so a reader who learned
"Seattle is yellow" is never misled. The palette is a colour-blind-validated
six-slot set; a seventh entity would wrap, which is the signal to facet or
fold into "Other" rather than add a hue.

**One axis per chart.** The GitHub panel wants to compare repos with 5k and
90k stars over time. A dual-axis chart would invent a correlation, so instead
the line chart plots *stars gained since first observation*, which is on a
common scale for everyone, and a separate bar chart shows absolute size.

**Partial failure publishes.** If Hacker News changes its markup, that source
fails, the other two are committed and deployed, and the dashboard shows a red
cell in HN's run strip. The job exits non-zero only when *every* source fails.
The alternative (fail the job, deploy nothing) makes one flaky upstream take
down the whole page.

**Data commits do not trigger CI.** `ci.yml` ignores pushes that only touch
`data/`, and pushes made with `GITHUB_TOKEN` never trigger `pipeline.yml`
(a GitHub rule that prevents loops). Code pushes trigger both.

## Where it would need to change

| If you want… | Change |
|---|---|
| A fourth source | `docs/adding-a-source.md`; no pipeline changes |
| Hourly runs | the cron line; watch GitHub's rate limit and repo growth |
| Years of HN history in the browser | pre-aggregate in `build` (per-day summaries) instead of shipping rows |
| A private data source | add a repo secret; read it in the source like `GITHUB_TOKEN` |
| More than ~100 MB of data | move raw snapshots to object storage (S3, R2) and keep only tidy in git |
| A backend (auth, per-user views, writes) | this stops being static; a small API on Fly/Render/Lambda with the same `scrapeboard` package |
| Charts without a CDN | vendor `plotly.min.js` into `site/` |
