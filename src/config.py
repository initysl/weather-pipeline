"""Project configuration: API endpoints, validation bounds and DB connection.

Cities live in the dim_city table, not here: see src/cities.py.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TIMEZONE = "Africa/Lagos"
COUNTRY_CODE = "NG"

# Open-Meteo: forecast API covers recent days; archive API covers history
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# The archive API's newest days can be missing or provisional for about this long
ARCHIVE_LAG_DAYS = 5

# Daily mode re-fetches this many recent days, covering the archive delay and missed runs
DAILY_PAST_DAYS = 7

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "windspeed_10m_max",
]

# Validation bounds; rows outside these are logged and dropped in transform
TEMP_MIN_C = -10
TEMP_MAX_C = 55

DB_USER =os.getenv("POSTGRES_USER", "weather")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_NAME = os.getenv("POSTGRES_DB", "weather")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
