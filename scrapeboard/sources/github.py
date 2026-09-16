"""Source 3 — an API that takes an (optional) API key (GitHub REST API).

Same shape as Open-Meteo — GET, JSON back — with one new concept: **secrets**.
GitHub serves anonymous requests but rate-limits them to 60/hour per IP. Send
a token and the limit is 5 000/hour. The token comes from the ``GITHUB_TOKEN``
environment variable:

* locally you can leave it unset (six repos = six requests, well under 60);
* in GitHub Actions the platform injects a short-lived token automatically
  (``secrets.GITHUB_TOKEN``) — no human ever copies a secret anywhere.

The rule the code enforces: **the key is read from the environment at request
time and never logged, stored, or written to disk.**

Docs: https://docs.github.com/en/rest/repos/repos#get-a-repository
"""

from __future__ import annotations

import json
import os
from typing import ClassVar

from scrapeboard import http
from scrapeboard.sources.base import Row, Source

API_URL = "https://api.github.com/repos/{full_name}"


def _auth_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class GitHubRepos(Source):
    name: ClassVar[str] = "github"
    key: ClassVar[tuple[str, ...]] = ("repo",)

    def fetch(self) -> bytes:
        # One request per repo; we bundle the responses into a single JSON
        # array so the raw snapshot is still "one file per run".
        payloads = []
        for full_name in self.config["repos"]:
            resp = http.get(API_URL.format(full_name=full_name), headers=_auth_headers())
            payloads.append(resp.json())
        return json.dumps(payloads).encode()

    def parse(self, raw: bytes) -> list[Row]:
        rows: list[Row] = []
        for item in json.loads(raw):
            rows.append(
                {
                    "repo": item["full_name"],
                    "stars": item["stargazers_count"],
                    "forks": item["forks_count"],
                    "open_issues": item["open_issues_count"],
                    "watchers": item["subscribers_count"],
                    "language": item.get("language") or "",
                    "pushed_at": item["pushed_at"],
                }
            )
        return rows
