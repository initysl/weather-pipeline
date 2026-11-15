"""Export queries against a throwaway city with a known full year (rolled back afterwards)."""
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from src.export import export_all


def add_city_with_year(conn, name: str, latitude: float, days: int, rain_every: int) -> int:
    """A city with `days` days of last year's data; every `rain_every`-th day has 5 mm of rain."""
    city_id = conn.execute(text("""
        INSERT INTO dim_city (name, state, latitude, longitude)
        VALUES (:name, 'Test State', :lat, 0) RETURNING city_id
    """), {"name": name, "lat": latitude}).scalar_one()
    start = date(date.today().year - 1, 1, 1)
    conn.execute(text("""
        INSERT INTO fact_daily_weather (city_id, weather_date, temp_max_c, temp_min_c,
                                        precipitation_mm, wind_speed_max_kmh)
        VALUES (:city_id, :d, 30, 20, :rain, 10)
    """), [{"city_id": city_id, "d": start + timedelta(days=i),
            "rain": 5.0 if i % rain_every == 0 else 0.0} for i in range(days)])
    return city_id


def test_exports_have_chart_ready_columns(conn, tmp_path):
    files = {p.stem: p for p in export_all(conn, tmp_path)}
    assert set(files) == {"annual_rainfall", "rainy_days_by_month", "this_week_vs_normal"}
    assert list(pd.read_csv(files["annual_rainfall"]).columns) == [
        "City", "State", "Year", "Rainfall (mm)", "Rainy days"]
    assert list(pd.read_csv(files["rainy_days_by_month"]).columns)[2:] == [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    assert "Difference (°C)" in pd.read_csv(files["this_week_vs_normal"]).columns


def test_annual_rainfall_totals_a_full_year(conn, tmp_path):
    add_city_with_year(conn, "Fullyear", latitude=50.0, days=365, rain_every=5)  # 73 rainy days
    export_all(conn, tmp_path)
    df = pd.read_csv(tmp_path / "annual_rainfall.csv")
    row = df[df["City"] == "Fullyear"].iloc[0]
    assert row["Rainy days"] == 73
    assert row["Rainfall (mm)"] == 73 * 5


def test_partial_year_is_left_out(conn, tmp_path):
    # Half a year of data would look like a very dry city, so it's excluded
    add_city_with_year(conn, "Halfyear", latitude=51.0, days=180, rain_every=5)
    export_all(conn, tmp_path)
    for name in ("annual_rainfall", "rainy_days_by_month"):
        assert "Halfyear" not in set(pd.read_csv(tmp_path / f"{name}.csv")["City"])


def test_monthly_table_is_ordered_north_to_south(conn, tmp_path):
    add_city_with_year(conn, "Farnorth", latitude=60.0, days=365, rain_every=7)
    export_all(conn, tmp_path)
    cities = list(pd.read_csv(tmp_path / "rainy_days_by_month.csv")["City"])
    assert cities[0] == "Farnorth"
