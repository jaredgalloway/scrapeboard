"""Filesystem layout, in one place.

Every path is derived from ``ROOT`` (the repo root), which is resolved relative
to this file rather than to the current working directory, so the CLI behaves
identically whether you run it from the repo root, a subdirectory, or CI.
Override with the ``SCRAPEBOARD_ROOT`` env var if you need to point the
pipeline at a scratch directory (the tests do this).
"""

from __future__ import annotations

import os
from pathlib import Path


def root() -> Path:
    env = os.environ.get("SCRAPEBOARD_ROOT")
    return Path(env).resolve() if env else Path(__file__).resolve().parent.parent


def config_file() -> Path:
    return root() / "config.yml"


def raw_dir(source: str) -> Path:
    """Immutable snapshots of exactly what the upstream returned, one file per run."""
    return root() / "data" / "raw" / source


def tidy_file(source: str) -> Path:
    """The append-only, one-row-per-observation table for a source."""
    return root() / "data" / "tidy" / f"{source}.csv"


def site_dir() -> Path:
    return root() / "site"


def site_data_dir() -> Path:
    """Where ``build`` writes the JSON the dashboard fetches. Gitignored; CI regenerates it."""
    return site_dir() / "data"
