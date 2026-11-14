"""Check which endpoint and parameters each mode sends, without calling the API."""
from datetime import date

import pytest

from src import extract, http_session
from src.config import ARCHIVE_URL, FORECAST_URL


class FakeResponse:
    ok = True
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def calls(monkeypatch, sample_response):
    recorded = []

    def fake_get(url, params, timeout):
        recorded.append((url, params))
        return FakeResponse(sample_response)

    monkeypatch.setattr(http_session.session, "get", fake_get)
    return recorded


def test_backfill_uses_archive_with_dates(calls, kano):
    extract.fetch_archive(kano, date(2024, 1, 1), date(2024, 12, 31), save_raw=False)
    url, params = calls[0]
    assert url == ARCHIVE_URL
    assert params["start_date"] == "2024-01-01"
    assert params["end_date"] == "2024-12-31"
    assert (params["latitude"], params["longitude"]) == (kano.latitude, kano.longitude)


def test_daily_uses_forecast_last_7_complete_days(calls, kano):
    extract.fetch_recent(kano, past_days=7, save_raw=False)
    url, params = calls[0]
    assert url == FORECAST_URL
    assert params["past_days"] == 7
    assert params["forecast_days"] == 0  # excludes today and the future
    assert "start_date" not in params


def test_reversed_dates_fail_before_calling_api(calls, kano):
    with pytest.raises(ValueError, match="after end_date"):
        extract.fetch_archive(kano, date(2024, 12, 31), date(2024, 1, 1), save_raw=False)
    assert calls == []


def test_raw_copy_is_named_by_city_and_state(calls, kano, tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "RAW_DIR", tmp_path)
    extract.fetch_recent(kano, save_raw=True)
    assert (tmp_path / "kano-kano-state_2026-11-07_2026-11-11.json").exists()
