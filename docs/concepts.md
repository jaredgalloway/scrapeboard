# Concepts

This page explains the operational ideas behind scrapeboard for a reader who
is comfortable with programs, data structures, and HTTP but has not run
anything on a schedule in production. Each section names the concept, shows
where it lives in this repo, and says what goes wrong without it.

## 1. Scraping is just HTTP, three ways

"Scraping" covers a spectrum from *the upstream wants you to have this data*
to *the upstream didn't think about you at all*.

| Flavour | Example here | Contract with upstream | Fragility |
|---|---|---|---|
| Open JSON API | Open-Meteo | documented URL + parameters, stable JSON schema | low |
| Authenticated JSON API | GitHub | same, plus a credential and a rate limit | low, but you can get locked out |
| HTML page | Hacker News | none; you depend on their template's CSS classes | high |

The code is nearly identical in all three cases (`http.get`, then a `parse`
function), which is the point: the *engineering* differences are in what
happens around the request. See `scrapeboard/sources/` where each module's
docstring explains its flavour.

**Politeness.** `scrapeboard/http.py` sets a User-Agent that names the project
and a URL. Anonymous default agents (`python-requests/2.32`) are the first
thing sites block. It also sets a timeout: the `requests` library has none by
default, and a hung upstream would otherwise hang the job until GitHub kills it
six hours later.

**Retries with back-off.** Transient failures (HTTP 429 "slow down", 502/503
"upstream hiccup") are retried three times with exponential pauses. Permanent
failures (404, 401) are not retried; that would only make a ban more likely.

## 2. Cron: running something on a schedule

A *cron expression* is five fields (`minute hour day-of-month month day-of-week`)
that describe a recurring time. `17 */6 * * *` means "minute 17 of every 6th
hour": 00:17, 06:17, 12:17, 18:17 UTC.

Where: `.github/workflows/pipeline.yml`, `on.schedule`.

Two practical details:

* **Don't pick minute 0.** Every scheduled job on GitHub fires at :00; the
  queue is longest then and runs can be delayed by 15 to 30 minutes. An odd
  minute gets you a runner faster.
* **Scheduled workflows go dormant** on repos with no commits for 60 days.
  Here the pipeline itself commits data every run, so it stays awake.

## 3. CI/CD: the same command, run by a robot

*Continuous integration* (CI) means every change is checked automatically.
*Continuous delivery/deployment* (CD) means the checked thing is shipped
automatically. GitHub Actions is the runner for both: a YAML file describes
a *workflow* (when to run, what steps), and GitHub boots a fresh Ubuntu VM
to execute it.

Where: `.github/workflows/ci.yml` (lint + tests on pull requests) and
`pipeline.yml` (scrape, commit, build, deploy).

The one rule this repo obeys strictly: **CI runs the same commands you do.**
`pixi run scrape`, `pixi run build`, `pixi run check`. If CI ran a special
script, "works on my machine" bugs would be inevitable. Pixi makes this
practical because `pixi.lock` pins every package to an exact version for both
your Mac and the Linux runner, so the two environments are identical down to
the byte.

**Why does the workflow commit to the repo?** The runner's disk is thrown away
after every run. The only durable storage we get for free is the git
repository itself, so scraped data is committed back. GitHub's built-in
`GITHUB_TOKEN` can push to the repo, and pushes made with that token do *not*
trigger new workflow runs (otherwise a commit-on-run pipeline would loop
forever).

**`concurrency`** in the workflow guarantees two runs never interleave. Without
it, a manual run and a scheduled run could both try to push and one would
fail on a non-fast-forward.

## 4. GitHub Pages: hosting without a server

GitHub Pages serves a folder of static files from a CDN at
`https://<user>.github.io/<repo>/`. "Static" means the server never runs code
on a request; it only returns files. That is enough for a dashboard when the
data is a JSON file the browser fetches and all the logic lives in
JavaScript.

Where: the `deploy` job in `pipeline.yml` uploads `site/` as an artifact and
`actions/deploy-pages` publishes it. In the repo settings, Pages is configured
with source "GitHub Actions" (not "deploy from a branch").

Trade-offs of static hosting:

* Free, fast, and nothing to patch or restart.
* No secrets can be used at view time; anything the page needs must be
  public. That is why the pipeline calls the GitHub API in CI and ships the
  *result* as JSON, rather than the browser calling GitHub directly.
* Updates are as fresh as the last deploy. The page polls `manifest.json`
  every five minutes and re-renders when `built_at` changes, so a tab left
  open updates itself after each pipeline run.

## 5. Secrets and API keys

A credential must never be in code, in a committed file, or in a log. The
convention is: **secrets enter through environment variables, at runtime.**

Where: `scrapeboard/sources/github.py` reads `GITHUB_TOKEN` from the
environment when it builds request headers. Locally you may leave it unset. In
CI, `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` injects a token that
GitHub mints for that run alone, scoped to this repo, expiring when the job
ends. No human ever copies it anywhere.

To add a key for a service that doesn't hand you one automatically: repo
Settings → Secrets and variables → Actions → New repository secret, then add
`SOME_KEY: ${{ secrets.SOME_KEY }}` under `env:` in the workflow step. GitHub
masks the value in logs. Locally, put it in your shell (or a 1Password-backed
`op run`), never in `config.yml`.

The one permission subtlety: `permissions:` at the top of the workflow lists
what the token may do (`contents: write` to push data, `pages: write` and
`id-token: write` to deploy). Least privilege by default.

## 6. Rate limits

APIs count your requests and refuse you past a threshold; scrapers get banned
by IP. Design so that a normal run is well under the limit *and* a failure
degrades gracefully:

* GitHub: 60 requests/hour anonymous, 5 000 with a token. Six repos every six
  hours is fine either way; the token is belt-and-braces.
* Open-Meteo: 10 000/day free, no key. One request per run fetches all cities.
* Hacker News: no published limit; one page every six hours is polite.

If you ever hit 429, `http.py` already backs off. If you keep hitting it,
lower the schedule frequency, not the retry count.

## 7. Idempotency

An operation is *idempotent* if doing it twice has the same effect as once.
Pipelines that run on a schedule get retried, re-run by hand, and occasionally
double-fired; if each run appended blindly, the table would fill with
duplicates.

Where: `pipeline.append_tidy` de-duplicates on `(observed_at, key columns)`
before writing. Running `scrape` twice in the same second produces the same
CSV. The test `test_append_is_idempotent_and_accumulates` pins this down.

## 8. Raw / tidy / view: the three-tier layout

* **Raw** (`data/raw/`) is exactly the bytes the upstream returned, one file
  per run. It is the audit trail. When your HTML parser breaks (it will), you
  fix the code and re-parse the snapshots; you cannot re-scrape the past.
* **Tidy** (`data/tidy/*.csv`) is one row per observation with an
  `observed_at` column, the shape pandas, DuckDB and notebooks want.
* **View** (`site/data/*.json`) is generated from tidy for one consumer, the
  browser. It is gitignored: derived data that can be rebuilt should never be
  committed, or it drifts from its source.

## 9. Observability, minimally

You cannot fix what you cannot see. The pipeline writes one line per
(run, source) to `data/runs.jsonl` with success, row count, duration and the
error text if any. The dashboard's top strip renders the last twenty runs per
source, uptime-monitor style, and the header turns red if the newest data is
older than fourteen hours (two missed runs).

The other half of observability is GitHub's own: the Actions tab shows every
run, its logs, and emails you on failure by default.

## 10. Environments: project-declares-its-tool

Nothing in this repo assumes a global Python. `pixi.toml` declares the
interpreter, every dependency, and every command; `pixi.lock` freezes the
solved versions per platform. `pixi install` reproduces the environment
anywhere, and `setup-pixi` in CI caches it so a run installs in seconds.

The Makefile exists for discoverability (`make help`) and muscle memory; each
target just calls `pixi run`.
