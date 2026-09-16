"""Registry of data sources. To add one: write a module, import it here, list it."""

from __future__ import annotations

from scrapeboard.sources.base import Row, Source
from scrapeboard.sources.github import GitHubRepos
from scrapeboard.sources.hackernews import HackerNews
from scrapeboard.sources.open_meteo import OpenMeteo

SOURCES: dict[str, type[Source]] = {cls.name: cls for cls in (OpenMeteo, HackerNews, GitHubRepos)}

__all__ = ["SOURCES", "Row", "Source"]
