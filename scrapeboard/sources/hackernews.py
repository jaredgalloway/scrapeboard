"""Source 2 — scraping an HTML page that was built for humans (Hacker News).

No API here: we download the front page and walk its DOM with BeautifulSoup.
This is the fragile kind of scraping — the selectors below (``tr.athing``,
``span.score`` ...) are an implicit contract with someone else's markup and
will break silently the day HN changes its template. Two defences:

1. ``tests/fixtures/hn_front.html`` pins the markup we *know* we can parse, so
   the test-suite tells you whether a break is in *our* code or *their* page.
2. ``parse()`` degrades gracefully (missing score → 0, missing URL → the item's
   own comments page) instead of raising on one odd row.
"""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scrapeboard import http
from scrapeboard.sources.base import Row, Source

_NUM = re.compile(r"(\d+)")


def _first_int(text: str | None, default: int = 0) -> int:
    m = _NUM.search(text or "")
    return int(m.group(1)) if m else default


class HackerNews(Source):
    name: ClassVar[str] = "hackernews"
    raw_ext: ClassVar[str] = "html"
    key: ClassVar[tuple[str, ...]] = ("item_id",)

    def fetch(self) -> bytes:
        return http.get(self.config["url"]).content

    def parse(self, raw: bytes) -> list[Row]:
        soup = BeautifulSoup(raw, "lxml")
        rows: list[Row] = []
        top_n = int(self.config.get("top_n", 30))
        for rank, story in enumerate(soup.select("tr.athing"), start=1):
            if rank > top_n:
                break
            title_a = story.select_one("span.titleline > a")
            if title_a is None:
                continue
            # The metadata (score, user, comments) lives in the *next* <tr>.
            meta = story.find_next_sibling("tr")
            subtext = meta.select_one("td.subtext") if meta else None
            item_id = story.get("id", "")
            url = title_a.get("href", "")
            if url.startswith("item?id="):
                url = f"https://news.ycombinator.com/{url}"
            comments_a = None
            if subtext:
                # The last <a> in the subtext is "N comments" or "discuss".
                links = subtext.select("a")
                comments_a = links[-1] if links else None
            rows.append(
                {
                    "item_id": item_id,
                    "rank": rank,
                    "title": title_a.get_text(strip=True),
                    "url": url,
                    "domain": urlparse(url).netloc.removeprefix("www."),
                    "points": _first_int(subtext.select_one("span.score").get_text())
                    if subtext and subtext.select_one("span.score")
                    else 0,
                    "author": subtext.select_one("a.hnuser").get_text(strip=True)
                    if subtext and subtext.select_one("a.hnuser")
                    else "",
                    "comments": _first_int(comments_a.get_text()) if comments_a else 0,
                }
            )
        return rows
