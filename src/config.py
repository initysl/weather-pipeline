"""Project configuration: cities, API endpoints and DB connection."""
import os

from dotenv import load_dotenv

load_dotenv()

# Cities we operate in: name -> (latitude, longitude)
CITIES = {
    "Kano": (12.0022, 8.5920),
    "Osogbo": (7.7827, 4.5418),
    "Ibadan": (7.3775, 3.9470),
    "Kaduna": (10.5105, 7.4165),
    "Lagos": (6.5244, 3.3792),
}

TIMEZONE = "Africa/Lagos"

# Open-Meteo: forecast API covers recent days; archive API covers history
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "rain_sum",
    "windspeed_10m_max",
]

DB_USER = os.getenv("POSTGRES_USER", "weather")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_NAME = os.getenv("POSTGRES_DB", "weather")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
