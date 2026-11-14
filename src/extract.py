"""Extract step: fetch raw daily weather JSON from Open-Meteo."""
import json
import logging
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import (
    ARCHIVE_URL,
    CITIES,
    DAILY_VARIABLES,
    FORECAST_URL,
    RAW_DIR,
    TIMEZONE,
)

logger = logging.getLogger(__name__)


def _build_session() -> requests.Session:
    """Session that retries connection errors and 429/5xx responses with backoff."""
    retry = Retry(
        total=4,
        backoff_factor=2,  # waits 0, 4, 8, 16s between attempts
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


_session = _build_session()


def fetch_archive(city: str, start_date: date, end_date: date, save_raw: bool = True) -> dict:
    """Backfill: historical data from the archive API, start to end inclusive."""
    if start_date > end_date:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")
    return _fetch(city, ARCHIVE_URL, {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }, save_raw)


def fetch_recent(city: str, past_days: int = 7, save_raw: bool = True) -> dict:
    """Daily: the last `past_days` complete days from the forecast API.

    forecast_days=0 means today (still in progress) and future days are excluded.
    """
    return _fetch(city, FORECAST_URL, {"past_days": past_days, "forecast_days": 0}, save_raw)


def _fetch(city: str, url: str, date_params: dict, save_raw: bool) -> dict:
    if city not in CITIES:
        raise ValueError(f"Unknown city {city!r}; add it to CITIES in config.py")

    lat, lon = CITIES[city]
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": TIMEZONE,
        **date_params,
    }

    logger.info("Fetching %s from %s %s", city, url, date_params)
    resp = _session.get(url, params=params, timeout=30)
    if not resp.ok:
        # Open-Meteo explains 4xx errors in a JSON "reason" field
        logger.error("Open-Meteo %s for %s: %s", resp.status_code, city, resp.text[:300])
    resp.raise_for_status()
    data = resp.json()

    dates = data.get("daily", {}).get("time")
    if not dates:
        raise ValueError(f"Unexpected response for {city}: no 'daily.time' dates")

    logger.info("Got %d rows for %s %s..%s", len(dates), city, dates[0], dates[-1])
    if save_raw:
        _save_raw(data, city, dates[0], dates[-1])
    return data


def _save_raw(data: dict, city: str, first: str, last: str) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{city.lower()}_{first}_{last}.json"
    path.write_text(json.dumps(data))
    logger.info("Saved raw copy to %s", path)
