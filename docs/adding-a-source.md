# Adding a source

Twenty minutes, five files. The example adds the USGS earthquake feed (a
GeoJSON API with no key).

## 1. Configuration: `config.yml`

```yaml
usgs:
  feed: "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
```

## 2. The source: `scrapeboard/sources/usgs.py`

```python
"""Source 4 — USGS earthquake feed (GeoJSON, no key)."""

from __future__ import annotations

import json
from typing import ClassVar

from scrapeboard import http
from scrapeboard.sources.base import Row, Source


class USGS(Source):
    name: ClassVar[str] = "usgs"
    key: ClassVar[tuple[str, ...]] = ("event_id",)   # with observed_at → unique

    def fetch(self) -> bytes:
        return http.get(self.config["feed"]).content

    def parse(self, raw: bytes) -> list[Row]:
        rows: list[Row] = []
        for f in json.loads(raw)["features"]:
            p, (lon, lat, depth) = f["properties"], f["geometry"]["coordinates"]
            rows.append({
                "event_id": f["id"],
                "magnitude": p["mag"],
                "place": p["place"],
                "lat": lat, "lon": lon, "depth_km": depth,
                "event_time_utc": p["time"],   # epoch ms; convert in build or JS
            })
        return rows
```

Rules the base class expects:

* `name` is the slug used for file names and the CLI.
* `key` lists the columns that, together with `observed_at`, identify one row.
  Get this right or de-duplication will silently drop rows (too few key
  columns) or keep duplicates (a key that changes every run, like a rank).
* `parse` must not do I/O and should degrade rather than raise on one odd
  record.
* Set `raw_ext = "html"` if the payload is HTML.

## 3. Register it: `scrapeboard/sources/__init__.py`

Import the class and add it to the tuple that builds `SOURCES`. If the source
produces many rows per run, add a history cap in `pipeline.HISTORY_DAYS`.

## 4. A fixture and tests

Fetch the real payload once and save it:

```bash
pixi run python -c "
from scrapeboard.pipeline import load_config
from scrapeboard.sources.usgs import USGS
open('tests/fixtures/usgs.json','wb').write(USGS(load_config()['usgs']).fetch())"
```

Then in `tests/test_sources.py` assert the shape you rely on: row count,
required columns, types, a value that must be positive. The fixture is the
contract; when the upstream changes, re-fetch it and see which assertion
breaks.

Run `pixi run check`.

## 5. The dashboard

Add a `<section class="panel">` to `site/index.html` with a `<div class="chart">`
and a `<table>`, and a `renderUSGS()` in `site/app.js` following `renderWeather`.
Reuse `baseLayout`, `lineTraces`, `renderTable`, `inRange`, and `latestRun`.
Add a fourth `.stage` to the pipeline strip with `data-source="usgs"`.

Preview with `pixi run pipeline && pixi run serve`. Commit, push; the pipeline
workflow runs on push and the new panel is live in a few minutes.
