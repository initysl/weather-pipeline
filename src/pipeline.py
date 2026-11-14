"""Run extract -> transform -> load for each city.

Examples (run from the project root):
    python -m src.pipeline --mode daily
    python -m src.pipeline --mode backfill --start 2024-01-01 --end 2026-11-08
    python -m src.pipeline --mode backfill --start 2026-11-01 --end 2026-11-07 --cities Kano Osogbo
"""
import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.config import ARCHIVE_LAG_DAYS, CITIES, DAILY_PAST_DAYS, TIMEZONE
from src.extract import fetch_archive, fetch_recent
from src.load import get_engine, load
from src.transform import transform

logger = logging.getLogger("pipeline")


def local_today() -> date:
    # The cities' local date, not the machine's
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load daily weather into Postgres.")
    parser.add_argument("--mode", choices=["daily", "backfill"], required=True,
                        help=f"daily: re-fetch the last {DAILY_PAST_DAYS} days (forecast API); "
                             "backfill: --start..--end (archive API)")
    parser.add_argument("--start", type=date.fromisoformat, help="backfill only, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="backfill only, YYYY-MM-DD")
    parser.add_argument("--cities", nargs="+", choices=list(CITIES), default=list(CITIES),
                        help="default: all cities in config")
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
        yesterday = local_today() - timedelta(days=1)
        if args.end > yesterday:
            parser.error(f"--end can be at most {yesterday}; today isn't over yet")
    return args


def run(mode: str, cities: list[str], start: date | None = None,
        end: date | None = None, save_raw: bool = True) -> list[str]:
    """Process each city independently; return the cities that failed."""
    if mode == "backfill" and end and end > local_today() - timedelta(days=ARCHIVE_LAG_DAYS):
        logger.warning("Archive data for the last %d days may be incomplete; "
                       "daily mode will overwrite them", ARCHIVE_LAG_DAYS)

    engine = get_engine()
    failed = []
    for city in cities:
        try:
            if mode == "daily":
                data = fetch_recent(city, DAILY_PAST_DAYS, save_raw=save_raw)
            else:
                assert start and end
                data = fetch_archive(city, start, end, save_raw=save_raw)
            df = transform(data, city)
            load(df, engine)  # one transaction per city
        except Exception:
            # Keep going so one bad city doesn't block the rest
            logger.exception("%s failed", city)
            failed.append(city)

    logger.info("Done (%s): %d ok, %d failed %s",
                mode, len(cities) - len(failed), len(failed), failed or "")
    return failed


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args(argv)
    failed = run(args.mode, args.cities, args.start, args.end, save_raw=not args.no_raw)
    # Non-zero exit tells a scheduler (cron etc.) that the run needs attention
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
