"""Extract step: fetch raw daily weather JSON from Open-Meteo.

Several cities can be fetched in one request: Open-Meteo accepts comma-separated
coordinates and returns one result per location, in the same order.
"""
import json
import logging
from datetime import date

from src import http_session
from src.cities import City
from src.config import (
    ARCHIVE_URL, DAILY_VARIABLES, FORECAST_URL, HTTP_TIMEOUT_S, RAW_DIR,
    REQUEST_DEADLINE_S, TIMEZONE,
)

logger = logging.getLogger(__name__)


def fetch_archive(cities: list[City], start_date: date, end_date: date,
                  save_raw: bool = True) -> list[dict]:
    """Backfill: historical data from the archive API, start to end inclusive."""
    if start_date > end_date:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")
    return _fetch(cities, ARCHIVE_URL, {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }, save_raw)


def fetch_recent(cities: list[City], past_days: int = 7, save_raw: bool = True) -> list[dict]:
    """Daily: the last `past_days` complete days from the forecast API.

    forecast_days=0 means today (still in progress) and future days are excluded.
    """
    return _fetch(cities, FORECAST_URL, {"past_days": past_days, "forecast_days": 0}, save_raw)


def _fetch(cities: list[City], url: str, date_params: dict, save_raw: bool) -> list[dict]:
    """One request for all `cities`; returns one raw result per city, in the same order."""
    if not cities:
        return []
    params = {
        "latitude": ",".join(str(c.latitude) for c in cities),
        "longitude": ",".join(str(c.longitude) for c in cities),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": TIMEZONE,
        **date_params,
    }
    who = cities[0].label if len(cities) == 1 else f"{len(cities)} cities"

    logger.info("Fetching %s from %s %s", who, url, date_params)
    with http_session.deadline(REQUEST_DEADLINE_S, f"Open-Meteo request for {who}"):
        resp = http_session.session.get(url, params=params, timeout=HTTP_TIMEOUT_S)
        if not resp.ok:
            # Open-Meteo explains 4xx errors in a JSON "reason" field
            logger.error("Open-Meteo %s for %s: %s", resp.status_code, who, resp.text[:300])
        resp.raise_for_status()
        data = resp.json()

    # A single location comes back as an object, several as a list
    results = data if isinstance(data, list) else [data]
    if len(results) != len(cities):
        raise ValueError(f"Asked for {len(cities)} locations, got {len(results)}")
    for i, result in enumerate(results):
        # Results carry their position as location_id (absent on the first one)
        if result.get("location_id", 0) != i:
            raise ValueError(f"Result {i} has location_id {result.get('location_id')}; order is unreliable")

    days = len(results[0].get("daily", {}).get("time", []))
    logger.info("Got %d days for %s", days, who)
    if save_raw:
        for city, result in zip(cities, results):
            _save_raw(result, city)
    return results


def _save_raw(data: dict, city: City) -> None:
    dates = data.get("daily", {}).get("time") or ["unknown"]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{city.slug}_{dates[0]}_{dates[-1]}.json"
    path.write_text(json.dumps(data))
