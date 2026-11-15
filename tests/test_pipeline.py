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
    [],                                                                      # no mode
])
def test_invalid_args_exit(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_cities_accept_name_and_state():
    args = parse_args(["--mode", "daily", "--cities", "Kano", "Ibadan, Oyo"])
    assert args.cities == ["Kano", "Ibadan, Oyo"]


# ---------- run(): failed cities get a second attempt ----------

from src import pipeline
from src.cities import City

CITIES = [City(1, "Kano", "Kano State", 12.0, 8.6), City(2, "Abuja", "FCT", 9.1, 7.5)]


@pytest.fixture
def fake_steps(monkeypatch):
    """Replace extract/transform/load; `fails[label]` = how many attempts fail first."""
    fails, attempts = {}, []

    def fake_fetch(city, *args, **kwargs):
        attempts.append(city.label)
        if fails.get(city.label, 0) > 0:
            fails[city.label] -= 1
            raise TimeoutError("Read timed out")
        return {}

    monkeypatch.setattr(pipeline, "fetch_recent", fake_fetch)
    monkeypatch.setattr(pipeline, "transform", lambda data, city: None)
    monkeypatch.setattr(pipeline, "load", lambda df, engine: 0)
    monkeypatch.setattr(pipeline, "get_engine", lambda: None)
    return fails, attempts


def test_city_that_recovers_on_second_attempt_counts_as_ok(fake_steps):
    fails, attempts = fake_steps
    fails["Abuja (FCT)"] = 1
    assert pipeline.run("daily", CITIES, retry_after=0) == []
    assert attempts == ["Kano (Kano State)", "Abuja (FCT)", "Abuja (FCT)"]


def test_city_that_keeps_failing_is_reported(fake_steps):
    fails, attempts = fake_steps
    fails["Abuja (FCT)"] = 5
    assert pipeline.run("daily", CITIES, retry_after=0) == ["Abuja (FCT)"]
    assert attempts.count("Abuja (FCT)") == 2  # one retry pass, not endless


def test_no_retry_pass_when_everything_succeeds(fake_steps):
    _, attempts = fake_steps
    assert pipeline.run("daily", CITIES, retry_after=0) == []
    assert len(attempts) == 2
