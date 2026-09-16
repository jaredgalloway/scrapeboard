"""One shared HTTP session with the three things every scraper needs.

1. **A User-Agent that identifies you.** Anonymous default UAs get blocked;
   polite scrapers say who they are and how to reach them.
2. **A timeout.** ``requests`` has *no* default timeout — a hung upstream would
   hang your CI job until the runner kills it (6 hours on GitHub Actions).
3. **Retries with back-off** on the transient status codes (429 rate-limited,
   5xx upstream trouble). Everything else fails fast.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scrapeboard import __version__

USER_AGENT = f"scrapeboard/{__version__} (+https://github.com/jaredgalloway/scrapeboard)"
DEFAULT_TIMEOUT = 20  # seconds; applied per request by ``get``


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=1.0,  # sleeps 1s, 2s, 4s between attempts
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


_SESSION: requests.Session | None = None


def get(url: str, *, params: dict | None = None, headers: dict | None = None) -> requests.Response:
    """GET with the shared session, a timeout, and ``raise_for_status``."""
    global _SESSION
    if _SESSION is None:
        _SESSION = make_session()
    resp = _SESSION.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp
