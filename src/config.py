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

# Cities that fail are tried once more after this pause, within the same run
RETRY_FAILED_AFTER_SECONDS = 60

# Seconds to wait (to connect, for a reply) before giving up on an API request
HTTP_TIMEOUT_S = (10, 30)

# Hard limit on one API request including its retries. HTTP_TIMEOUT_S only limits
# silence between bytes, so a server sending a trickle of data could otherwise hold a
# request open indefinitely.
REQUEST_DEADLINE_S = 180

# Daily mode asks for this many cities in one API request (Open-Meteo accepts a list of
# coordinates). Backfills stay at one city per request: a multi-year request counts as
# many API calls, and several at once could exceed the per-minute limit.
CITIES_PER_DAILY_REQUEST = 50

# Seconds to wait for a database connection before giving up
DB_CONNECT_TIMEOUT_S = 15

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

DB_USER = os.getenv("POSTGRES_USER", "weather")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_NAME = os.getenv("POSTGRES_DB", "weather")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")


def _database_url() -> str:
    """A full DATABASE_URL (hosted Postgres) wins; otherwise build one from POSTGRES_* (Docker)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    # Some providers hand out postgres://, which SQLAlchemy 2 doesn't accept
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


DATABASE_URL = _database_url()
