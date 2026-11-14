from datetime import date

import pytest

from src.transform import transform


def make_data(**overrides):
    daily = {
        "time": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "temperature_2m_max": [31.2, 32.0, 30.5],
        "temperature_2m_min": [18.0, 19.1, 17.4],
        "precipitation_sum": [0.0, 1.5, 0.0],
        "windspeed_10m_max": [12.0, 14.3, 9.8],
    }
    daily.update(overrides)
    return {"daily": daily}


def test_shapes_clean_dataframe():
    df = transform(make_data(), "Kano")
    assert list(df.columns) == [
        "city", "weather_date", "temp_max_c", "temp_min_c",
        "precipitation_mm", "wind_speed_max_kmh",
    ]
    assert len(df) == 3
    assert (df["city"] == "Kano").all()
    assert df.loc[0, "weather_date"] == date(2025, 1, 1)


def test_missing_date_fails():
    with pytest.raises(ValueError, match="missing or unparseable date"):
        transform(make_data(time=["2025-01-01", None, "2025-01-03"]), "Kano")


def test_gap_in_dates_fails():
    with pytest.raises(ValueError, match="missing dates"):
        transform(make_data(time=["2025-01-01", "2025-01-02", "2025-01-04"]), "Kano")


def test_duplicate_date_fails():
    with pytest.raises(ValueError, match="duplicate dates"):
        transform(make_data(time=["2025-01-01", "2025-01-01", "2025-01-02"]), "Kano")


def test_out_of_range_rows_are_logged_and_dropped(caplog):
    df = transform(
        make_data(temperature_2m_max=[31.2, 60.0, 30.5], precipitation_sum=[0.0, 0.0, -1.0]),
        "Kano",
    )
    assert list(df["weather_date"]) == [date(2025, 1, 1)]
    assert "temp_max_c outside" in caplog.text
    assert "precipitation_mm < 0" in caplog.text


def test_max_below_min_is_dropped(caplog):
    df = transform(make_data(temperature_2m_min=[18.0, 35.0, 17.4]), "Kano")
    assert date(2025, 1, 2) not in set(df["weather_date"])
    assert "temp_max_c < temp_min_c" in caplog.text


def test_null_measurement_is_kept():
    df = transform(make_data(precipitation_sum=[0.0, None, 0.0]), "Kano")
    assert len(df) == 3
    assert df["precipitation_mm"].isna().sum() == 1
