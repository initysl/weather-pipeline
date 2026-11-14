"""Extract step: fetch raw daily weather JSON from Open-Meteo."""
import json
import logging
from datetime import date, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import (
    ARCHIVE_LAG_DAYS,
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


def _pick_url(end_date: date) -> str:
    """Archive for settled history, forecast API for the last few days."""
    archive_cutoff = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    return ARCHIVE_URL if end_date <= archive_cutoff else FORECAST_URL


def fetch_daily_weather(
    city: str, start_date: date, end_date: date, save_raw: bool = True
) -> dict:
    """Return Open-Meteo's raw JSON for one city between two dates (inclusive)."""
    if city not in CITIES:
        raise ValueError(f"Unknown city {city!r}; add it to CITIES in config.py")
    if start_date > end_date:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")

    lat, lon = CITIES[city]
    url = _pick_url(end_date)
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": TIMEZONE,
    }

    logger.info("Fetching %s %s..%s from %s", city, start_date, end_date, url)
    resp = _session.get(url, params=params, timeout=30)
    if not resp.ok:
        # Open-Meteo explains 4xx errors in a JSON "reason" field
        logger.error("Open-Meteo %s for %s: %s", resp.status_code, city, resp.text[:300])
    resp.raise_for_status()
    data = resp.json()

    if "daily" not in data or "time" not in data["daily"]:
        raise ValueError(f"Unexpected response for {city}: no 'daily.time' field")

    logger.info("Got %d rows for %s %s..%s",
                len(data["daily"]["time"]), city, start_date, end_date)

    if save_raw:
        _save_raw(data, city, start_date, end_date)
    return data


def _save_raw(data: dict, city: str, start_date: date, end_date: date) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{city.lower()}_{start_date}_{end_date}.json"
    path.write_text(json.dumps(data))
    logger.info("Saved raw copy to %s", path)
