"""Source 1 — a public JSON API with no authentication (Open-Meteo).

The simplest possible kind of scraping: an HTTP GET returns structured JSON
designed for machines. We ask for the *current* conditions of several cities
in one request (the API accepts comma-separated coordinate lists) and turn the
response into one row per city.

Docs: https://open-meteo.com/en/docs
"""

from __future__ import annotations

import json
from typing import ClassVar

from scrapeboard import http
from scrapeboard.sources.base import Row, Source

API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → short human labels (subset that matters).
WMO_CODES = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Showers",
    81: "Heavy showers",
    82: "Violent showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ hail",
    99: "Thunderstorm w/ heavy hail",
}


class OpenMeteo(Source):
    name: ClassVar[str] = "open_meteo"
    key: ClassVar[tuple[str, ...]] = ("city",)

    def fetch(self) -> bytes:
        cities = self.config["cities"]
        params = {
            "latitude": ",".join(str(c["lat"]) for c in cities),
            "longitude": ",".join(str(c["lon"]) for c in cities),
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "timezone": "UTC",
        }
        return http.get(API_URL, params=params).content

    def parse(self, raw: bytes) -> list[Row]:
        payload = json.loads(raw)
        # Open-Meteo returns a single object for one location but a list for
        # many. Normalise so the loop below never has to care.
        if isinstance(payload, dict):
            payload = [payload]
        rows: list[Row] = []
        for city, item in zip(self.config["cities"], payload, strict=True):
            cur = item["current"]
            code = int(cur["weather_code"])
            rows.append(
                {
                    "city": city["name"],
                    "lat": city["lat"],
                    "lon": city["lon"],
                    "temperature_c": cur["temperature_2m"],
                    "humidity_pct": cur["relative_humidity_2m"],
                    "wind_kmh": cur["wind_speed_10m"],
                    "weather_code": code,
                    "weather": WMO_CODES.get(code, f"code {code}"),
                    "api_time_utc": cur["time"],
                }
            )
        return rows
