"""Command-line entry point: ``scrapeboard <command>``.

Every step of the pipeline is a sub-command so that a human at a laptop and a
GitHub Actions runner execute *exactly* the same thing. (If CI ran some special
script, "works on my machine" bugs would be inevitable.)
"""

from __future__ import annotations

import functools
import http.server
import logging
from typing import Annotated

import typer

from scrapeboard import paths, pipeline
from scrapeboard.sources import SOURCES

app = typer.Typer(help=__doc__, no_args_is_help=True, add_completion=False)


@app.callback()
def _setup(verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def sources() -> None:
    """List the registered data sources."""
    for name, cls in SOURCES.items():
        doc = (cls.__module__ and __import__(cls.__module__, fromlist=["_"]).__doc__ or "").strip()
        typer.echo(f"{name:<12} {doc.splitlines()[0] if doc else ''}")


@app.command()
def scrape(
    source: Annotated[
        list[str] | None,
        typer.Option("--source", "-s", help="Only run this source (repeatable)."),
    ] = None,
) -> None:
    """Fetch every source, snapshot raw payloads, append tidy rows."""
    results = pipeline.scrape(source)
    failed = [r for r in results if not r.ok]
    typer.echo(f"{len(results) - len(failed)}/{len(results)} sources ok")
    # Partial failure is *not* fatal: the successful sources' data is on disk
    # and should still be published. Total failure is.
    if failed and len(failed) == len(results):
        raise typer.Exit(code=1)


@app.command()
def build() -> None:
    """Render data/tidy/*.csv into site/data/*.json for the dashboard."""
    manifest = pipeline.build()
    typer.echo(f"built {len(manifest['sources'])} source feed(s) → {paths.site_data_dir()}")


@app.command()
def serve(port: Annotated[int, typer.Option("--port", "-p")] = 8000) -> None:
    """Serve ./site locally (what GitHub Pages will serve in production)."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(paths.site_dir())
    )
    typer.echo(f"serving {paths.site_dir()} on http://localhost:{port}  (Ctrl-C to stop)")
    http.server.ThreadingHTTPServer(("", port), handler).serve_forever()


if __name__ == "__main__":
    app()
