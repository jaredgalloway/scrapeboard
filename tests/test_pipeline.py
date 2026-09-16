"""Pipeline tests: raw snapshot, tidy append/dedupe, run log, build output."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from scrapeboard import paths, pipeline
from scrapeboard.sources.base import Source


class FakeSource(Source):
    """A source with no network and a controllable payload."""

    name = "fake"
    key = ("k",)

    def __init__(self, rows):
        super().__init__({})
        self.rows = rows
        self.calls = 0

    def fetch(self) -> bytes:
        self.calls += 1
        return json.dumps(self.rows).encode()

    def parse(self, raw: bytes):
        return json.loads(raw)


class BrokenSource(FakeSource):
    def fetch(self) -> bytes:
        raise ConnectionError("upstream down")


T1 = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 16, 16, 0, tzinfo=UTC)


def test_run_source_writes_raw_tidy_and_runlog(sandbox_root):
    src = FakeSource([{"k": "a", "v": 1}, {"k": "b", "v": 2}])
    result = pipeline.run_source(src, T1)
    assert result.ok and result.rows == 2

    raw = list(paths.raw_dir("fake").iterdir())
    assert [p.name for p in raw] == ["20260916T100000Z.json"]

    tidy = pd.read_csv(paths.tidy_file("fake"))
    assert list(tidy.columns) == ["observed_at", "k", "v"]
    assert tidy["observed_at"].unique().tolist() == [T1.isoformat()]

    run_log = (sandbox_root / "data/runs.jsonl").read_text().splitlines()
    runs = [json.loads(line) for line in run_log]
    assert runs[0]["source"] == "fake" and runs[0]["ok"] is True


def test_append_is_idempotent_and_accumulates(sandbox_root):
    src = FakeSource([{"k": "a", "v": 1}])
    pipeline.run_source(src, T1)
    pipeline.run_source(src, T1)  # same instant again → no duplicate
    assert len(pd.read_csv(paths.tidy_file("fake"))) == 1
    src.rows = [{"k": "a", "v": 5}]
    pipeline.run_source(src, T2)  # later run → new row
    tidy = pd.read_csv(paths.tidy_file("fake"))
    assert tidy["v"].tolist() == [1, 5]


def test_failure_is_logged_not_raised(sandbox_root):
    result = pipeline.run_source(BrokenSource([]), T1)
    assert not result.ok and "upstream down" in result.error
    assert not paths.tidy_file("fake").exists()
    runs = (sandbox_root / "data/runs.jsonl").read_text()
    assert '"ok": false' in runs


def test_scrape_rejects_unknown_source(sandbox_root):
    with pytest.raises(SystemExit):
        pipeline.scrape(["nope"])


def test_build_emits_feed_and_manifest(sandbox_root, monkeypatch):
    src = FakeSource([{"k": "a", "v": 1}])
    monkeypatch.setitem(pipeline.__dict__, "SOURCES", {"fake": FakeSource})
    pipeline.run_source(src, T1)
    pipeline.run_source(src, T2)
    manifest = pipeline.build()

    out = paths.site_data_dir()
    feed = json.loads((out / "fake.json").read_text())
    assert feed["columns"] == ["observed_at", "k", "v"]
    assert len(feed["rows"]) == 2
    assert manifest["sources"]["fake"]["runs"] == 2
    assert manifest["sources"]["fake"]["last_observed"].startswith("2026-09-16T16:00")
    assert json.loads((out / "manifest.json").read_text()) == manifest
    assert len(json.loads((out / "runs.json").read_text())) == 2


def test_build_trims_history(sandbox_root, monkeypatch):
    monkeypatch.setitem(pipeline.__dict__, "SOURCES", {"fake": FakeSource})
    monkeypatch.setitem(pipeline.HISTORY_DAYS, "fake", 1)
    src = FakeSource([{"k": "a", "v": 1}])
    pipeline.run_source(src, datetime(2026, 9, 1, tzinfo=UTC))
    pipeline.run_source(src, T1)
    pipeline.build()
    feed = json.loads((paths.site_data_dir() / "fake.json").read_text())
    assert len(feed["rows"]) == 1  # the 2026-09-01 row is older than 1 day before max
