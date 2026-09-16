"""Parser tests replay saved payloads — no network, deterministic, fast.

If one of these fails after an upstream changed its format, re-fetch the
fixture (see docs/adding-a-source.md) and fix the parser; the raw snapshots in
``data/raw/`` let you re-parse history afterwards.
"""

from __future__ import annotations

import responses

from scrapeboard.pipeline import load_config
from scrapeboard.sources import SOURCES
from scrapeboard.sources.github import API_URL as GH_URL
from scrapeboard.sources.github import GitHubRepos
from scrapeboard.sources.hackernews import HackerNews
from scrapeboard.sources.open_meteo import OpenMeteo


def test_registry_names_match_classes():
    for name, cls in SOURCES.items():
        assert cls.name == name
        assert cls.key, f"{name} must declare key columns"


def test_open_meteo_parse(fixture_bytes):
    src = OpenMeteo(load_config()["open_meteo"])
    rows = src.parse(fixture_bytes("open_meteo.json"))
    assert len(rows) == 6
    seattle = rows[0]
    assert seattle["city"] == "Seattle"
    assert isinstance(seattle["temperature_c"], int | float)
    assert seattle["weather"] and not seattle["weather"].startswith("code ")
    assert {r["city"] for r in rows} == {c["name"] for c in src.config["cities"]}


def test_open_meteo_single_location_payload_is_normalised():
    src = OpenMeteo({"cities": [{"name": "X", "lat": 0, "lon": 0}]})
    payload = (
        b'{"current": {"time": "2026-01-01T00:00", "temperature_2m": 1.5, '
        b'"relative_humidity_2m": 50, "wind_speed_10m": 3.0, "weather_code": 999}}'
    )
    rows = src.parse(payload)
    assert rows[0]["weather"] == "code 999"  # unknown code degrades, doesn't raise


def test_hackernews_parse(fixture_bytes):
    src = HackerNews(load_config()["hackernews"])
    rows = src.parse(fixture_bytes("hackernews.html"))
    assert len(rows) == 30
    assert [r["rank"] for r in rows] == list(range(1, 31))
    for r in rows:
        assert r["item_id"].isdigit()
        assert r["title"]
        assert r["url"].startswith("http")
        assert r["points"] >= 0 and r["comments"] >= 0
    assert any(r["points"] > 0 for r in rows)


def test_hackernews_top_n_is_respected(fixture_bytes):
    rows = HackerNews({"url": "x", "top_n": 5}).parse(fixture_bytes("hackernews.html"))
    assert len(rows) == 5


def test_hackernews_tolerates_missing_subtext():
    html = (
        b'<table><tr class="athing" id="1"><td><span class="titleline">'
        b'<a href="item?id=1">Ask HN</a></span></td></tr></table>'
    )
    rows = HackerNews({"url": "x"}).parse(html)
    assert rows == [
        {
            "item_id": "1",
            "rank": 1,
            "title": "Ask HN",
            "url": "https://news.ycombinator.com/item?id=1",
            "domain": "news.ycombinator.com",
            "points": 0,
            "author": "",
            "comments": 0,
        }
    ]


def test_github_parse(fixture_bytes):
    cfg = load_config()["github"]
    rows = GitHubRepos(cfg).parse(fixture_bytes("github.json"))
    assert [r["repo"] for r in rows] == cfg["repos"]
    assert all(r["stars"] > 0 for r in rows)


@responses.activate
def test_github_fetch_sends_token_only_when_set(monkeypatch):
    src = GitHubRepos({"repos": ["o/r"]})
    responses.get(GH_URL.format(full_name="o/r"), json={"full_name": "o/r"})

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    src.fetch()
    assert "Authorization" not in responses.calls[0].request.headers

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_dummy")
    src.fetch()
    assert responses.calls[1].request.headers["Authorization"] == "Bearer ghp_dummy"
