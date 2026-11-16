"""Run extract -> transform -> load for each city.

Examples (run from the project root):
    python -m src.pipeline --mode daily
    python -m src.pipeline --mode backfill --start 2024-01-01 --end 2026-11-08
    python -m src.pipeline --mode daily --cities Kano "Ibadan, Oyo"

Cities come from the dim_city table (manage them with `python -m src.cities`).
"""
import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.cities import City, list_cities, resolve
from src.config import (
    ARCHIVE_LAG_DAYS, CITIES_PER_DAILY_REQUEST, DAILY_PAST_DAYS, RETRY_FAILED_AFTER_SECONDS, TIMEZONE,
)
from src.extract import fetch_archive, fetch_recent
from src.load import get_engine, load
from src.transform import transform

logger = logging.getLogger("pipeline")


def local_today() -> date:
    # The cities' local date, not the machine's
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def yesterday() -> date:
    return local_today() - timedelta(days=1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load daily weather into Postgres.")
    parser.add_argument("--mode", choices=["daily", "backfill"], required=True,
                        help=f"daily: re-fetch the last {DAILY_PAST_DAYS} days (forecast API); "
                             "backfill: --start..--end (archive API)")
    parser.add_argument("--start", type=date.fromisoformat, help="backfill only, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="backfill only, YYYY-MM-DD")
    parser.add_argument("--cities", nargs="+", metavar="CITY",
                        help="'Name' or 'Name, State' (default: every active city in dim_city)")
    parser.add_argument("--no-raw", action="store_true",
                        help="don't save raw JSON to data/raw/")
    args = parser.parse_args(argv)

    if args.mode == "daily":
        if args.start or args.end:
            parser.error("--start/--end are only for --mode backfill")
    else:
        if not (args.start and args.end):
            parser.error("--mode backfill needs --start and --end")
        if args.start > args.end:
            parser.error(f"--start {args.start} is after --end {args.end}")
        if args.end > yesterday():
            parser.error(f"--end can be at most {yesterday()}; today isn't over yet")
    return args


def _batches(cities: list[City], mode: str) -> list[list[City]]:
    """Daily: many cities per API request. Backfill: one (multi-year requests are heavy)."""
    size = CITIES_PER_DAILY_REQUEST if mode == "daily" else 1
    return [cities[i:i + size] for i in range(0, len(cities), size)]


def _process_batch(batch: list[City], mode: str, start: date | None, end: date | None,
                   save_raw: bool, engine) -> list[City]:
    """Fetch a batch in one request, then transform and load each city on its own.

    Returns the cities that failed. If the request fails, the whole batch failed;
    after that, one city's bad data never affects the others.
    """
    try:
        if mode == "daily":
            results = fetch_recent(batch, DAILY_PAST_DAYS, save_raw=save_raw)
        else:
            assert start and end
            results = fetch_archive(batch, start, end, save_raw=save_raw)
    except Exception:
        logger.exception("Fetching %s failed", ", ".join(c.label for c in batch))
        return list(batch)

    failed = []
    for city, data in zip(batch, results):
        try:
            df = transform(data, city)
            load(df, engine)  # one transaction per city
        except Exception:
            # Keep going so one bad city doesn't block the rest
            logger.exception("%s failed", city.label)
            failed.append(city)
    return failed


def _process(cities: list[City], mode: str, start: date | None, end: date | None,
             save_raw: bool, engine) -> list[City]:
    failed = []
    for batch in _batches(cities, mode):
        failed += _process_batch(batch, mode, start, end, save_raw, engine)
    return failed


def run(mode: str, cities: list[City], start: date | None = None,
        end: date | None = None, save_raw: bool = True,
        retry_after: float = RETRY_FAILED_AFTER_SECONDS) -> list[str]:
    """Process every city; return the labels of cities that still failed.

    Cities that fail are tried once more after `retry_after` seconds, so a brief
    API outage doesn't fail the whole run. (Each request already retries quickly;
    this second pass covers problems lasting a minute or two.)
    """
    if mode == "backfill" and end and end > local_today() - timedelta(days=ARCHIVE_LAG_DAYS):
        logger.warning("Archive data for the last %d days may be incomplete; "
                       "daily mode will overwrite them", ARCHIVE_LAG_DAYS)

    engine = get_engine()
    failed = _process(cities, mode, start, end, save_raw, engine)

    if failed:
        logger.warning("Retrying %d failed %s in %ds: %s", len(failed),
                       "city" if len(failed) == 1 else "cities", retry_after,
                       [c.label for c in failed])
        time.sleep(retry_after)
        failed = _process(failed, mode, start, end, save_raw, engine)

    labels = [c.label for c in failed]
    logger.info("Done (%s): %d ok, %d failed %s",
                mode, len(cities) - len(failed), len(failed), labels or "")
    return labels


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args(argv)

    with get_engine().connect() as conn:
        tracked = list_cities(conn)
    try:
        cities = resolve(tracked, args.cities) if args.cities else tracked
    except ValueError as e:
        logger.error("%s", e)
        return 2
    if not cities:
        logger.error("No active cities in dim_city. Add one with: python -m src.cities add <name>")
        return 1

    failed = run(args.mode, cities, args.start, args.end, save_raw=not args.no_raw)
    # Non-zero exit tells a scheduler (cron etc.) that the run needs attention
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
