"""Transform step: turn Open-Meteo JSON into a clean, validated DataFrame."""
import logging
import pandas as pd

from src.cities import City
from src.config import TEMP_MAX_C, TEMP_MIN_C

logger = logging.getLogger(__name__)

# API field -> our column name (matches fact_daily_weather)
COLUMN_MAP = {
    "time": "weather_date",
    "temperature_2m_max": "temp_max_c",
    "temperature_2m_min": "temp_min_c",
    "precipitation_sum": "precipitation_mm",
    "windspeed_10m_max": "wind_speed_max_kmh",
}
MEASURES = ["temp_max_c", "temp_min_c", "precipitation_mm", "wind_speed_max_kmh"]


def transform(data: dict, city: City) -> pd.DataFrame:
    """Return one validated row per date: city_id, weather_date and the four measures.

    Raises ValueError if dates are missing, duplicated or have gaps.
    Rows that fail range/consistency checks are logged and dropped.
    """
    label = city.label  # for log and error messages
    daily = data.get("daily")
    if not daily:
        raise ValueError(f"{label}: response has no 'daily' section")

    missing_cols = set(COLUMN_MAP) - set(daily)
    if missing_cols:
        raise ValueError(f"{label}: response is missing fields {sorted(missing_cols)}")

    # columns= keeps only the fields we use; rename then always returns a DataFrame
    df = pd.DataFrame(daily, columns=list(COLUMN_MAP)).rename(columns=COLUMN_MAP)
    df["weather_date"] = pd.to_datetime(df["weather_date"], errors="coerce").dt.date
    for col in MEASURES:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.insert(0, "city_id", city.city_id)

    _check_dates(df, label)
    df = _drop_invalid_rows(df, label)

    nulls = {col: int(df[col].isna().sum()) for col in MEASURES}
    nulls = {col: n for col, n in nulls.items() if n}
    if nulls:
        logger.warning("%s: null values kept as NULL: %s", label, nulls)

    logger.info("%s: %d rows passed validation", label, len(df))
    return df.reset_index(drop=True)


def _check_dates(df: pd.DataFrame, city: str) -> None:
    """Dates are the key, so any problem with them stops the run."""
    if df["weather_date"].isna().any():
        raise ValueError(f"{city}: {df['weather_date'].isna().sum()} rows have a missing or unparseable date")

    dupes = df.loc[df["weather_date"].duplicated(), "weather_date"]
    if not dupes.empty:
        raise ValueError(f"{city}: duplicate dates {sorted(dupes.unique())}")

    expected = pd.date_range(df["weather_date"].min(), df["weather_date"].max()).date
    gaps = sorted(set(expected) - set(df["weather_date"]))
    if gaps:
        raise ValueError(f"{city}: missing dates {gaps}")


def _out_of_range(s: pd.Series, lo: float, hi: float) -> pd.Series:
    # NULLs aren't out of range; between() alone would flag them
    return s.notna() & ~s.between(lo, hi)


def _drop_invalid_rows(df: pd.DataFrame, city: str) -> pd.DataFrame:
    rules = {
        f"temp_max_c outside {TEMP_MIN_C}..{TEMP_MAX_C}": _out_of_range(df["temp_max_c"], TEMP_MIN_C, TEMP_MAX_C),
        f"temp_min_c outside {TEMP_MIN_C}..{TEMP_MAX_C}": _out_of_range(df["temp_min_c"], TEMP_MIN_C, TEMP_MAX_C),
        "precipitation_mm < 0": df["precipitation_mm"] < 0,
        "wind_speed_max_kmh < 0": df["wind_speed_max_kmh"] < 0,
        "temp_max_c < temp_min_c": df["temp_max_c"] < df["temp_min_c"],
    }

    bad = pd.Series(False, index=df.index)
    for rule, mask in rules.items():
        if mask.any():
            logger.warning("%s: %d rows failed '%s': %s",
                           city, mask.sum(), rule, df.loc[mask].to_dict("records"))
            bad |= mask

    if bad.any():
        logger.warning("%s: dropped %d of %d rows", city, bad.sum(), len(df))
    return df.drop(index=df.index[bad])
