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


# ---------- run(): batching and the second attempt ----------

from src import pipeline
from src.cities import City

CITIES = [City(1, "Kano", "Kano State", 12.0, 8.6), City(2, "Abuja", "FCT", 9.1, 7.5)]


@pytest.fixture
def fake_steps(monkeypatch):
    """Replace extract/transform/load.

    fails["request"]: how many API requests fail first
    fails[label]:     how many times that city's transform fails first
    """
    fails, requests_made, loaded = {}, [], []

    def fake_fetch(cities, *args, **kwargs):
        requests_made.append([c.label for c in cities])
        if fails.get("request", 0) > 0:
            fails["request"] -= 1
            raise TimeoutError("Read timed out")
        return [{} for _ in cities]

    def fake_transform(data, city):
        if fails.get(city.label, 0) > 0:
            fails[city.label] -= 1
            raise ValueError("bad data")
        return city

    monkeypatch.setattr(pipeline, "fetch_recent", fake_fetch)
    monkeypatch.setattr(pipeline, "fetch_archive", fake_fetch)
    monkeypatch.setattr(pipeline, "transform", fake_transform)
    monkeypatch.setattr(pipeline, "load", lambda city, engine: loaded.append(city.label))
    monkeypatch.setattr(pipeline, "get_engine", lambda: None)
    return fails, requests_made, loaded


def test_daily_fetches_all_cities_in_one_request(fake_steps):
    _, requests_made, loaded = fake_steps
    assert pipeline.run("daily", CITIES, retry_after=0) == []
    assert requests_made == [["Kano (Kano State)", "Abuja (FCT)"]]
    assert loaded == ["Kano (Kano State)", "Abuja (FCT)"]


def test_backfill_fetches_one_city_per_request(fake_steps):
    _, requests_made, _ = fake_steps
    pipeline.run("backfill", CITIES, date(2024, 1, 1), date(2024, 1, 31), retry_after=0)
    assert requests_made == [["Kano (Kano State)"], ["Abuja (FCT)"]]


def test_failed_request_is_retried_once_and_recovers(fake_steps):
    fails, requests_made, loaded = fake_steps
    fails["request"] = 1
    assert pipeline.run("daily", CITIES, retry_after=0) == []
    assert len(requests_made) == 2
    assert loaded == ["Kano (Kano State)", "Abuja (FCT)"]


def test_request_that_keeps_failing_reports_every_city(fake_steps):
    fails, requests_made, _ = fake_steps
    fails["request"] = 5
    assert pipeline.run("daily", CITIES, retry_after=0) == ["Kano (Kano State)", "Abuja (FCT)"]
    assert len(requests_made) == 2  # one retry pass, not endless


def test_one_bad_city_does_not_block_the_others(fake_steps):
    fails, requests_made, loaded = fake_steps
    fails["Abuja (FCT)"] = 5
    assert pipeline.run("daily", CITIES, retry_after=0) == ["Abuja (FCT)"]
    assert loaded == ["Kano (Kano State)"]
    assert requests_made[1] == ["Abuja (FCT)"]  # the retry only re-fetches the failed city
