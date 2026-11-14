import copy
import json
import os
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from src.cities import City

_SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "sample_response.json").read_text())


@pytest.fixture
def sample_response():
    """A real 5-day Open-Meteo response for Kano. Each test gets its own copy to modify."""
    return copy.deepcopy(_SAMPLE)


@pytest.fixture
def kano():
    return City(city_id=1, name="Kano", state="Kano State", latitude=12.0022, longitude=8.592)


@pytest.fixture
def conn():
    """A DB connection inside a transaction that is always rolled back.

    Skipped locally if Postgres isn't running; in CI a missing database is a failure.
    """
    from src.load import get_engine
    try:
        connection = get_engine().connect()
    except OperationalError:
        if os.getenv("CI"):  # set by GitHub Actions
            raise
        pytest.skip("Postgres not running (docker compose up -d)")
    tx = connection.begin()
    yield connection
    tx.rollback()
    connection.close()
