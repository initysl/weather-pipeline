"""Integration tests against Postgres.

Each test runs inside a transaction that is rolled back (see the `conn` fixture),
so real data is untouched.
"""
import math
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from src.load import BATCH_SIZE, upsert_weather


@pytest.fixture
def city_id(conn):
    """A throwaway city that only exists inside the test's transaction."""
    return conn.execute(text("""
        INSERT INTO dim_city (name, state, latitude, longitude)
        VALUES ('Testville', 'Test State', 0, 0) RETURNING city_id
    """)).scalar_one()


def make_df(city_id, temp_max=31.0, precip=0.0):
    return pd.DataFrame({
        "city_id": [city_id, city_id],
        "weather_date": [date(1999, 1, 1), date(1999, 1, 2)],
        "temp_max_c": [temp_max, 32.0],
        "temp_min_c": [18.0, 19.0],
        "precipitation_mm": [precip, 0.0],
        "wind_speed_max_kmh": [10.0, 12.0],
    })


def rows(conn, city_id):
    return conn.execute(text("""
        SELECT weather_date, temp_max_c, precipitation_mm
        FROM fact_daily_weather WHERE city_id = :id ORDER BY weather_date
    """), {"id": city_id}).all()


def test_rerun_does_not_duplicate(conn, city_id):
    upsert_weather(conn, make_df(city_id))
    upsert_weather(conn, make_df(city_id))
    assert len(rows(conn, city_id)) == 2


def test_rerun_updates_values(conn, city_id):
    upsert_weather(conn, make_df(city_id, temp_max=31.0))
    upsert_weather(conn, make_df(city_id, temp_max=33.5))
    assert float(rows(conn, city_id)[0].temp_max_c) == 33.5


def test_nan_is_stored_as_null(conn, city_id):
    upsert_weather(conn, make_df(city_id, precip=float("nan")))
    assert rows(conn, city_id)[0].precipitation_mm is None


def test_large_load_is_batched(conn, city_id):
    # 2,500 rows -> 3 statements of up to BATCH_SIZE rows, not 2,500 round trips
    n = 2500
    df = pd.DataFrame({
        "city_id": city_id,
        "weather_date": pd.date_range("1990-01-01", periods=n).date,
        "temp_max_c": 31.0, "temp_min_c": 20.0, "precipitation_mm": 0.0, "wind_speed_max_kmh": 9.0,
    })
    inserts = []

    def record(conn_, cursor, statement, params, context, executemany):
        if statement.lstrip().startswith("INSERT INTO fact_daily_weather"):
            inserts.append(executemany)

    event.listen(conn, "before_cursor_execute", record)
    try:
        assert upsert_weather(conn, df) == n
        assert upsert_weather(conn, df) == n  # and the rerun still doesn't duplicate
    finally:
        event.remove(conn, "before_cursor_execute", record)

    expected = math.ceil(n / BATCH_SIZE)
    assert inserts == [False] * (2 * expected)  # single multi-row statements, never executemany
    assert len(rows(conn, city_id)) == n


def test_unknown_city_id_is_rejected(conn):
    # The foreign key to dim_city refuses weather for a city that doesn't exist
    with pytest.raises(IntegrityError):
        upsert_weather(conn, make_df(city_id=-1))
