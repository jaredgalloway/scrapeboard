"""Orchestration: the part that turns *sources* into *files on disk*.

The data flows through three tiers, and each tier is a folder::

    upstream ──fetch──▶ data/raw/<source>/<run>.json   (immutable snapshot)
                 └──parse──▶ data/tidy/<source>.csv    (append-only table)
                                  └──build──▶ site/data/<source>.json  (dashboard feed)

Why three tiers instead of writing the dashboard JSON directly?

* **raw** is your audit trail and your safety net. When a parser breaks (and
  HTML parsers always break eventually) you can fix the code and re-parse
  history instead of losing it. Snapshots are cheap; re-scraping the past is
  impossible.
* **tidy** is the analysis-friendly form: one row per observation, one column
  per variable, every row stamped with ``observed_at``. This is what you would
  load into pandas/DuckDB/a notebook. It is CSV so ``git diff`` stays readable.
* **site/data** is a *view*: the tidy tables re-shaped and trimmed for the
  browser. It is generated, gitignored, and rebuilt by CI on every run, so it
  can never drift from the tidy data.

A fourth file, ``data/runs.jsonl``, is the run log: one line per (run, source)
with success/failure, row count and duration. The dashboard reads it to show
"source health" — the beginnings of observability.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import pandas as pd
import yaml

from scrapeboard import paths
from scrapeboard.sources import SOURCES, Row, Source

log = logging.getLogger("scrapeboard")

#: How much history each source ships to the browser (days). ``None`` = all.
#: HN produces 30 rows per run, so unbounded history would eventually make the
#: page slow to load; the others are one row per city/repo per run.
HISTORY_DAYS: dict[str, int | None] = {"hackernews": 30, "open_meteo": None, "github": None}


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def run_stamp(now: datetime) -> str:
    """Filesystem-safe, sortable, timezone-explicit: ``20260916T101500Z``."""
    return now.strftime("%Y%m%dT%H%M%SZ")


def load_config() -> dict:
    with paths.config_file().open() as fh:
        return yaml.safe_load(fh)


# ── scrape ───────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    run_at: str
    source: str
    ok: bool
    rows: int
    duration_s: float
    error: str = ""


def snapshot_raw(source: Source, raw: bytes, now: datetime) -> None:
    out_dir = paths.raw_dir(source.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{run_stamp(now)}.{source.raw_ext}").write_bytes(raw)


def append_tidy(source: Source, rows: list[Row], now: datetime) -> int:
    """Append rows to the source's CSV, de-duplicated on (observed_at, *key).

    Idempotency matters: if CI retries a job, or you run ``scrape`` twice in a
    row while debugging, the table must not grow duplicate observations.
    """
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    new.insert(0, "observed_at", now.isoformat())
    path = paths.tidy_file(source.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        combined = pd.concat([old, new.astype(str)], ignore_index=True)
    else:
        combined = new.astype(str)
    subset = ["observed_at", *source.key]
    combined = combined.drop_duplicates(subset=subset, keep="last")
    combined = combined.sort_values(subset).reset_index(drop=True)
    combined.to_csv(path, index=False)
    return len(new)


def run_source(source: Source, now: datetime) -> RunResult:
    t0 = time.perf_counter()
    try:
        raw = source.fetch()
        snapshot_raw(source, raw, now)
        rows = source.parse(raw)
        n = append_tidy(source, rows, now)
        elapsed = round(time.perf_counter() - t0, 2)
        result = RunResult(now.isoformat(), source.name, True, n, elapsed)
        log.info("%-12s ok  %3d rows in %.1fs", source.name, n, result.duration_s)
    except Exception as exc:  # noqa: BLE001 — one bad source must not sink the run
        result = RunResult(
            now.isoformat(),
            source.name,
            False,
            0,
            round(time.perf_counter() - t0, 2),
            f"{type(exc).__name__}: {exc}",
        )
        log.error("%-12s FAILED %s\n%s", source.name, result.error, traceback.format_exc())
    _log_run(result)
    return result


def _log_run(result: RunResult) -> None:
    path = paths.root() / "data" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(asdict(result)) + "\n")


def scrape(only: list[str] | None = None) -> list[RunResult]:
    config = load_config()
    now = utcnow()
    names = only or list(SOURCES)
    unknown = set(names) - set(SOURCES)
    if unknown:
        raise SystemExit(f"unknown source(s): {sorted(unknown)}; known: {sorted(SOURCES)}")
    return [run_source(SOURCES[name](config.get(name, {})), now) for name in names]


# ── build ────────────────────────────────────────────────────────────────────


def _tidy_frame(name: str) -> pd.DataFrame | None:
    path = paths.tidy_file(name)
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    return df


def _trim(df: pd.DataFrame, days: int | None) -> pd.DataFrame:
    if days is None or df.empty:
        return df
    cutoff = df["observed_at"].max() - pd.Timedelta(days=days)
    return df[df["observed_at"] >= cutoff]


def build() -> dict:
    """Write ``site/data/*.json`` + ``manifest.json``; return the manifest."""
    out = paths.site_data_dir()
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"built_at": utcnow().isoformat(), "sources": {}}

    for name in SOURCES:
        df = _tidy_frame(name)
        if df is None:
            log.warning("%-12s no tidy data yet — skipping", name)
            continue
        entry = {
            "rows_total": int(len(df)),
            "runs": int(df["observed_at"].nunique()),
            "first_observed": df["observed_at"].min().isoformat(),
            "last_observed": df["observed_at"].max().isoformat(),
        }
        shipped = _trim(df, HISTORY_DAYS.get(name))
        payload = {
            "source": name,
            "columns": list(shipped.columns),
            "rows": json.loads(shipped.to_json(orient="records", date_format="iso")),
        }
        (out / f"{name}.json").write_text(json.dumps(payload, separators=(",", ":")))
        entry["rows_shipped"] = int(len(shipped))
        manifest["sources"][name] = entry
        log.info("%-12s %5d rows → site/data/%s.json", name, len(shipped), name)

    runs_path = paths.root() / "data" / "runs.jsonl"
    runs: list[dict] = []
    if runs_path.exists():
        runs = [json.loads(line) for line in runs_path.read_text().splitlines() if line.strip()]
    (out / "runs.json").write_text(json.dumps(runs[-200:]))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
