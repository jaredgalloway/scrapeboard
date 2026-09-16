"""scrapeboard — the *Hello, world* of a scrape → transform → publish pipeline.

Three layers, each a module:

* ``sources/``  — one class per upstream (a JSON API, an HTML page, an
  authenticated API). Each knows how to ``fetch()`` raw bytes and ``parse()``
  them into tidy rows. Nothing else.
* ``pipeline``  — the orchestration: snapshot raw payloads to ``data/raw/``,
  append tidy rows to ``data/tidy/<source>.csv``, and ``build`` the JSON files
  the dashboard reads from ``site/data/``.
* ``cli``       — a thin Typer front-end so every step is a shell command
  (``scrapeboard scrape``, ``scrapeboard build``, ...). CI and humans run the
  exact same commands.
"""

__version__ = "0.1.0"
