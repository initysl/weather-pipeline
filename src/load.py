"""Load step: upsert validated rows into Postgres without creating duplicates."""
import logging
from functools import lru_cache
import pandas as pd
from sqlalchemy import (
    Column, Connection, Date, Engine, Integer, MetaData, Numeric, Table, create_engine, func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, insert

from src.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Rows per INSERT statement. Each statement is one round trip to the database, so
# against a hosted Postgres ~0.1s away, 1,000 rows take one trip instead of 1,000.
# (Postgres allows 65,535 parameters per statement; 1,000 rows x 6 columns is 6,000.)
BATCH_SIZE = 1000

# Mirrors sql/schema.sql, which remains the source of truth (this never creates tables)
fact_daily_weather = Table(
    "fact_daily_weather", MetaData(),
    Column("city_id", Integer, primary_key=True),
    Column("weather_date", Date, primary_key=True),
    Column("temp_max_c", Numeric(5, 2)),
    Column("temp_min_c", Numeric(5, 2)),
    Column("precipitation_mm", Numeric(6, 2)),
    Column("wind_speed_max_kmh", Numeric(6, 2)),
    Column("loaded_at", TIMESTAMP(timezone=True)),
)

MEASURES = ["temp_max_c", "temp_min_c", "precipitation_mm", "wind_speed_max_kmh"]
FACT_COLUMNS = ["city_id", "weather_date", *MEASURES]


def _upsert_statement(rows: list[dict]):
    """INSERT ... VALUES (row 1), (row 2), ... ON CONFLICT (city_id, weather_date) DO UPDATE.

    One row per (city_id, weather_date): reruns overwrite instead of duplicating.
    A single statement can't contain the same key twice (Postgres raises "cannot
    affect row a second time"); transform already rejects duplicate dates.
    """
    stmt = insert(fact_daily_weather).values(rows)
    return stmt.on_conflict_do_update(
        index_elements=["city_id", "weather_date"],
        set_={**{col: stmt.excluded[col] for col in MEASURES}, "loaded_at": func.now()},
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def upsert_weather(conn: Connection, df: pd.DataFrame) -> int:
    """Upsert transformed rows using an open connection; return rows written.

    The caller owns the transaction, so this can be tested and rolled back.
    """
    if df.empty:
        logger.info("Nothing to load")
        return 0

    # city_id comes from dim_city; the foreign key rejects any that doesn't exist
    out = df[FACT_COLUMNS]
    # NaN would be stored as the NUMERIC value 'NaN', not NULL, so convert it
    out = out.astype(object).where(out.notna(), None)
    records = out.to_dict(orient="records")

    for i in range(0, len(records), BATCH_SIZE):
        conn.execute(_upsert_statement(records[i:i + BATCH_SIZE]))

    logger.info("Upserted %d rows for city_id %s", len(records), sorted(set(df["city_id"])))
    return len(records)


def load(df: pd.DataFrame, engine: Engine | None = None) -> int:
    """Upsert rows in a single transaction: all rows commit, or none do."""
    with (engine or get_engine()).begin() as conn:
        return upsert_weather(conn, df)
