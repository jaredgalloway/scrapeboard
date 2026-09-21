# Operations runbook

Everything here assumes you are in the repo with `pixi install` done. Commands
in this repo never need a global Python.

## Where to look first

* **The dashboard's pipeline strip.** A red cell names the failing source;
  hover it for the error text.
* **GitHub → Actions → pipeline.** Every run, with logs. Failed runs email you.
* **`data/runs.jsonl`** is the same information on disk, one JSON line per
  (run, source).

## A source is failing

1. Reproduce locally: `pixi run scrape -s hackernews`. The traceback prints.
2. If it is a parse error, the upstream changed. Save the new payload as the
   fixture (`data/raw/hackernews/<newest>.html` is already the exact bytes;
   copy it to `tests/fixtures/hackernews.html`), run `pixi run test`, fix the
   parser until it passes, and check that the older raw snapshots still parse
   too.
3. If it is a network error (timeout, 5xx after retries, 429), do nothing for
   a few hours, then run it again. Persistent 429 or 403 means the User-Agent
   or frequency needs adjusting; scrape less often first.
4. The other sources kept publishing throughout. Nothing to restore.

## The page is stale

The header turns red when the newest data is over fourteen hours old.

* Actions tab shows no recent runs: expected, scheduled scraping is off (see
  "Running the scraper" below). Trigger a run, or turn the schedule on. If a
  schedule *was* on and stopped, GitHub pauses schedules on repos with 60 days
  of no commits: Actions → pipeline → Enable workflow.
* Runs exist but fail at "Commit new data": someone pushed to `main` between
  checkout and push. The `git pull --rebase` normally handles it; if a real
  conflict in `data/` occurred, re-run the workflow. It is idempotent.
* Runs succeed but the page didn't change: hard-refresh. The page polls
  `manifest.json` every five minutes with cache disabled, but the CDN may
  hold `index.html` for up to ten minutes after a deploy.

## Re-parse history after fixing a parser

Raw snapshots make this a one-off script rather than a loss:

```bash
pixi run python - <<'EOF'
from datetime import datetime, UTC
from pathlib import Path
from scrapeboard import paths, pipeline
from scrapeboard.sources import SOURCES
name = "hackernews"
src = SOURCES[name](pipeline.load_config()[name])
paths.tidy_file(name).unlink(missing_ok=True)       # rebuild from scratch
for snap in sorted(paths.raw_dir(name).iterdir()):
    when = datetime.strptime(snap.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    pipeline.append_tidy(src, src.parse(snap.read_bytes()), when)
EOF
pixi run build && pixi run serve
```

Commit the regenerated CSV.

## Running the scraper

Scheduled scraping is **off** by default. Nothing touches the upstreams until
you ask. There are three ways to ask, cheapest first.

### 1. Locally, no publish

```bash
pixi run pipeline   # scrape every source, then build site/data/
pixi run serve      # look at it on http://localhost:8000
```

`data/` now has new snapshots and rows. Leave them uncommitted if this was
just a look, or commit them to keep the history.

### 2. Locally, then publish

```bash
pixi run scrape
git add data && git commit -m "data: scrape $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push
```

A push to `main` runs the `pipeline` workflow in *deploy-only* mode: it
builds from the committed `data/` and publishes, without scraping again. So
this path also publishes any code change.

### 3. On GitHub, from anywhere

```bash
pixi run scrape-remote      # or: gh workflow run pipeline
```

or Actions → pipeline → Run workflow. The runner scrapes, commits the data
to `main` as `github-actions[bot]`, builds, and deploys. Pull afterwards to
get the new rows locally. This is the same thing the schedule would do.

### Turn the schedule on

In `.github/workflows/pipeline.yml`, uncomment the two `schedule:` lines:

```yaml
on:
  schedule:
    - cron: "17 */6 * * *"
  workflow_dispatch:
  push:
    branches: [main]
```

Commit and push. GitHub reads the schedule from `main`, so the first
automatic run happens at the next matching time (here 00:17, 06:17, 12:17,
18:17 UTC). Change the cron line to change the cadence; keep an odd minute.
To turn it off again, comment the lines back out. Nothing else in the
workflow needs to change: the scrape steps run for every trigger except
`push`.

### Emergency stop

Actions → pipeline → "…" → Disable workflow. This blocks *every* trigger,
manual and push included, until you re-enable it. Prefer commenting out the
cron for the normal case.

## Secrets

The only credential is `GITHUB_TOKEN`, minted by GitHub per run. There is
nothing to rotate. If you add a source that needs a key, it goes in
Settings → Secrets and variables → Actions, is referenced in the workflow
under `env:`, and is read with `os.environ` in the source. Never print it and
never write it to `data/`.

Locally, keep such keys out of files in the repo. `op run --env-file` (1Password)
or a shell `export` are both fine.

## Cost and quotas

| Thing | Free allowance | Our use |
|---|---|---|
| Actions minutes (public repo) | unlimited | ~1 min per run, 4 runs/day |
| Pages bandwidth | 100 GB/month soft limit | a few MB/day |
| Pages site size | 1 GB | ~5 MB |
| Repo size | 1 GB soft, 5 GB hard | grows ~40 MB/year at current sources |
| GitHub API | 5 000 req/h with token | 6 req/run |

Nothing here has a card attached. If the repo were private, Actions minutes
would be metered (2 000/month free) and Pages would require a paid plan.

## Local development loop

```bash
pixi run check            # lint + tests, ~2 s
pixi run scrape -s github # one source, real network
pixi run build && pixi run serve
```

Open http://localhost:8000. The page reads `site/data/`, which `build` just
wrote, so refresh after each `build`.
