from datetime import date

import pytest

from src.pipeline import parse_args


def test_daily_needs_no_dates():
    args = parse_args(["--mode", "daily"])
    assert args.mode == "daily" and args.start is None


def test_daily_rejects_dates():
    with pytest.raises(SystemExit):
        parse_args(["--mode", "daily", "--start", "2026-01-01"])


def test_backfill_parses_dates():
    args = parse_args(["--mode", "backfill", "--start", "2024-01-01", "--end", "2024-12-31"])
    assert (args.start, args.end) == (date(2024, 1, 1), date(2024, 12, 31))


@pytest.mark.parametrize("argv", [
    ["--mode", "backfill", "--start", "2024-01-01"],                         # no --end
    ["--mode", "backfill", "--start", "2024-12-31", "--end", "2024-01-01"],  # reversed
    ["--mode", "backfill", "--start", "2024-01-01", "--end", "2999-01-01"],  # future
    ["--mode", "daily", "--cities", "Atlantis"],                             # unknown city
    [],                                                                      # no mode
])
def test_invalid_args_exit(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)
