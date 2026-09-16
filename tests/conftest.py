"""Shared fixtures. The key trick: point the pipeline at a temp dir.

``SCRAPEBOARD_ROOT`` redirects every path in ``scrapeboard.paths`` so tests can
write raw/tidy/site files freely without touching the real ``data/`` folder.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def fixture_bytes():
    def _load(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return _load


@pytest.fixture
def sandbox_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throw-away repo root with the real config.yml and site/ copied in."""
    shutil.copy(REPO_ROOT / "config.yml", tmp_path / "config.yml")
    shutil.copytree(REPO_ROOT / "site", tmp_path / "site", ignore=shutil.ignore_patterns("data"))
    monkeypatch.setenv("SCRAPEBOARD_ROOT", str(tmp_path))
    return tmp_path
