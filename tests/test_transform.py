from datetime import date

import pytest

from src.transform import transform

EXPECTED_COLUMNS = [
    "city_id", "weather_date", "temp_max_c", "temp_min_c",
    "precipitation_mm", "wind_speed_max_kmh",
]


def test_column_names(sample_response, kano):
    df = transform(sample_response, kano)
    assert list(df.columns) == EXPECTED_COLUMNS


def test_data_types(sample_response, kano):
    df = transform(sample_response, kano)
    assert all(isinstance(d, date) for d in df["weather_date"])
    for col in EXPECTED_COLUMNS[2:]:
        assert df[col].dtype == "float64", col
    assert (df["city_id"] == kano.city_id).all()


def test_values_are_kept(sample_response, kano):
    df = transform(sample_response, kano)
    assert len(df) == 5
    first = df.iloc[0]
    assert first["weather_date"] == date(2026, 11, 7)
    assert first["temp_max_c"] == 36.6
    assert first["wind_speed_max_kmh"] == 14.9


def test_missing_date_fails(sample_response, kano):
    sample_response["daily"]["time"][2] = None
    with pytest.raises(ValueError, match="missing or unparseable date"):
        transform(sample_response, kano)


def test_gap_in_dates_fails(sample_response, kano):
    sample_response["daily"]["time"][2] = "2026-11-20"
    with pytest.raises(ValueError, match="missing dates"):
        transform(sample_response, kano)


def test_duplicate_date_fails(sample_response, kano):
    sample_response["daily"]["time"][1] = "2026-11-07"
    with pytest.raises(ValueError, match="duplicate dates"):
        transform(sample_response, kano)


def test_missing_field_fails(sample_response, kano):
    del sample_response["daily"]["precipitation_sum"]
    with pytest.raises(ValueError, match="precipitation_sum"):
        transform(sample_response, kano)


def test_out_of_range_rows_are_logged_and_dropped(sample_response, kano, caplog):
    sample_response["daily"]["temperature_2m_max"][1] = 60.0
    sample_response["daily"]["precipitation_sum"][3] = -1.0
    df = transform(sample_response, kano)
    assert len(df) == 3
    assert date(2026, 11, 8) not in set(df["weather_date"])
    assert date(2026, 11, 10) not in set(df["weather_date"])
    assert "temp_max_c outside" in caplog.text
    assert "precipitation_mm < 0" in caplog.text


def test_max_below_min_is_dropped(sample_response, kano, caplog):
    sample_response["daily"]["temperature_2m_min"][0] = 40.0
    df = transform(sample_response, kano)
    assert date(2026, 11, 7) not in set(df["weather_date"])
    assert "temp_max_c < temp_min_c" in caplog.text


def test_null_measurement_is_kept(sample_response, kano, caplog):
    sample_response["daily"]["precipitation_sum"][4] = None
    df = transform(sample_response, kano)
    assert len(df) == 5
    assert df["precipitation_mm"].isna().sum() == 1
    assert "null values kept" in caplog.text
