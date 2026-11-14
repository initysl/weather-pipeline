"""Load step: upsert validated rows into Postgres without creating duplicates."""
import logging
from functools import lru_cache
import pandas as pd
from sqlalchemy import Connection, Engine, create_engine, text

from src.config import CITIES, DATABASE_URL

logger = logging.getLogger(__name__)

# Insert cities from config, or refresh their coordinates if they already exist
UPSERT_CITY = text("""
    INSERT INTO dim_city (name, latitude, longitude)
    VALUES (:name, :latitude, :longitude)
    ON CONFLICT (name) DO UPDATE
        SET latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude
""")

# One row per (city_id, weather_date): reruns overwrite instead of duplicating
UPSERT_WEATHER = text("""
    INSERT INTO fact_daily_weather (
        city_id, weather_date, temp_max_c, temp_min_c,
        precipitation_mm, wind_speed_max_kmh
    )
    VALUES (
        :city_id, :weather_date, :temp_max_c, :temp_min_c,
        :precipitation_mm, :wind_speed_max_kmh
    )
    ON CONFLICT (city_id, weather_date) DO UPDATE
        SET temp_max_c         = EXCLUDED.temp_max_c,
            temp_min_c         = EXCLUDED.temp_min_c,
            precipitation_mm   = EXCLUDED.precipitation_mm,
            wind_speed_max_kmh = EXCLUDED.wind_speed_max_kmh,
            loaded_at          = now()
""")

FACT_COLUMNS = [
    "city_id", "weather_date", "temp_max_c", "temp_min_c",
    "precipitation_mm", "wind_speed_max_kmh",
]


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def sync_cities(conn: Connection) -> dict[str, int]:
    """Make sure every city in config exists in dim_city; return {name: city_id}."""
    conn.execute(UPSERT_CITY, [
        {"name": name, "latitude": lat, "longitude": lon}
        for name, (lat, lon) in CITIES.items()
    ])
    rows = conn.execute(text("SELECT name, city_id FROM dim_city"))
    return {name: city_id for name, city_id in rows}


def upsert_weather(conn: Connection, df: pd.DataFrame) -> int:
    """Upsert transformed rows using an open connection; return rows written.

    The caller owns the transaction, so this can be tested and rolled back.
    """
    if df.empty:
        logger.info("Nothing to load")
        return 0

    city_ids = sync_cities(conn)
    unknown = set(df["city"]) - set(city_ids)
    if unknown:
        raise ValueError(f"Cities not in dim_city: {sorted(unknown)}")

    out = df.assign(city_id=df["city"].map(city_ids))[FACT_COLUMNS]
    # NaN would be stored as the NUMERIC value 'NaN', not NULL, so convert it
    out = out.astype(object).where(out.notna(), None)
    records = out.to_dict(orient="records")

    conn.execute(UPSERT_WEATHER, records)
    logger.info("Upserted %d rows for %s", len(records), sorted(set(df["city"])))
    return len(records)


def load(df: pd.DataFrame, engine: Engine | None = None) -> int:
    """Upsert rows in a single transaction: all rows commit, or none do."""
    with (engine or get_engine()).begin() as conn:
        return upsert_weather(conn, df)
