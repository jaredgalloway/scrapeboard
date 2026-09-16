"""The contract every data source implements.

A *source* is deliberately tiny: it turns "the internet" into a list of flat
dictionaries (rows). It does **not** know about files, CSVs, the dashboard, or
scheduling — that is the pipeline's job. Keeping sources this narrow is what
makes them testable offline: ``parse()`` is a pure function of bytes you can
save to ``tests/fixtures/`` once and replay forever.

Every row must carry the ``observed_at`` column (an ISO-8601 UTC timestamp
stamped by the pipeline) plus the source's own ``KEY`` columns, which together
identify one observation. Re-running the pipeline within the same minute must
not create duplicate rows — see ``pipeline.append_tidy``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

Row = dict[str, Any]


class Source(ABC):
    #: Short slug used for file names (``data/tidy/<name>.csv``) and the CLI.
    name: ClassVar[str]
    #: File extension for the raw snapshot (``json`` or ``html``).
    raw_ext: ClassVar[str] = "json"
    #: Columns that, together with ``observed_at``, uniquely identify a row.
    key: ClassVar[tuple[str, ...]]

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def fetch(self) -> bytes:
        """Hit the network once and return the raw payload exactly as received."""

    @abstractmethod
    def parse(self, raw: bytes) -> list[Row]:
        """Turn a raw payload into tidy rows. Pure; no I/O; safe to unit-test."""
