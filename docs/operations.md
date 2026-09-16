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
   a few hours. Retries are automatic on the next schedule. Persistent 429 or
   403 means the User-Agent or frequency needs adjusting; lower the cron
   frequency first.
4. The other sources kept publishing throughout. Nothing to restore.

## The page is stale

The header turns red when the newest data is over fourteen hours old.

* Actions tab shows no recent runs: the schedule was disabled (repos with
  60 days of no commits, or a manual disable). Actions → pipeline → Enable
  workflow, then Run workflow.
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

## Pause or change the schedule

* Pause: Actions → pipeline → "…" → Disable workflow. Re-enable the same way.
* Change frequency: edit the `cron:` line in `.github/workflows/pipeline.yml`.
  Keep the odd minute.
* Run now: Actions → pipeline → Run workflow (or `gh workflow run pipeline`).

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
