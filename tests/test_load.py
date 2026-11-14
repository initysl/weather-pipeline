"""Integration tests against the Docker Postgres.

Each test runs inside a transaction that is rolled back, so real data is untouched.
Skipped if the database isn't running.
"""
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from src.load import get_engine, upsert_weather


@pytest.fixture
def conn():
    try:
        connection = get_engine().connect()
    except OperationalError:
        pytest.skip("Postgres not running (docker compose up -d)")
    tx = connection.begin()
    yield connection
    tx.rollback()
    connection.close()


def make_df(temp_max=31.0, precip=0.0):
    return pd.DataFrame({
        "city": ["Kano", "Kano"],
        "weather_date": [date(1999, 1, 1), date(1999, 1, 2)],
        "temp_max_c": [temp_max, 32.0],
        "temp_min_c": [18.0, 19.0],
        "precipitation_mm": [precip, 0.0],
        "wind_speed_max_kmh": [10.0, 12.0],
    })


def kano_rows(conn):
    return conn.execute(text("""
        SELECT f.weather_date, f.temp_max_c, f.precipitation_mm
        FROM fact_daily_weather f JOIN dim_city c USING (city_id)
        WHERE c.name = 'Kano' AND f.weather_date < '2000-01-01'
        ORDER BY f.weather_date
    """)).all()


def test_rerun_does_not_duplicate(conn):
    upsert_weather(conn, make_df())
    upsert_weather(conn, make_df())
    assert len(kano_rows(conn)) == 2


def test_rerun_updates_values(conn):
    upsert_weather(conn, make_df(temp_max=31.0))
    upsert_weather(conn, make_df(temp_max=33.5))
    assert float(kano_rows(conn)[0].temp_max_c) == 33.5


def test_nan_is_stored_as_null(conn):
    upsert_weather(conn, make_df(precip=float("nan")))
    assert kano_rows(conn)[0].precipitation_mm is None


def test_unknown_city_fails(conn):
    df = make_df().assign(city="Atlantis")
    with pytest.raises(ValueError, match="Atlantis"):
        upsert_weather(conn, df)
