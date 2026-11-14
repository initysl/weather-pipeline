import copy
import json
from pathlib import Path

import pytest

_SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "sample_response.json").read_text())


@pytest.fixture
def sample_response():
    """A real 5-day Open-Meteo response for Kano. Each test gets its own copy to modify."""
    return copy.deepcopy(_SAMPLE)
