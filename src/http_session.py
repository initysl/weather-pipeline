"""One shared HTTP session for every Open-Meteo call (weather and geocoding)."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session() -> requests.Session:
    """Session that retries connection errors and 429/5xx responses with backoff."""
    retry = Retry(
        total=4,
        backoff_factor=2,  # waits 0, 4, 8, 16s between attempts
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


session = build_session()
