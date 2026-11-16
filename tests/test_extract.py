"""Check what each mode asks Open-Meteo for and how responses are split, without the network."""
import copy
import socket
import threading
import time
from datetime import date

import pytest
import requests

from src import extract, http_session
from src.cities import City
from src.config import ARCHIVE_URL, FORECAST_URL

ABUJA = City(2, "Abuja", "FCT", 9.05785, 7.49508)


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
def api(monkeypatch, sample_response):
    """Fake Open-Meteo: answers like the real API (an object for one location, a list for several)."""
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params))
        n = len(str(params["latitude"]).split(","))
        if n == 1:
            return FakeResponse(sample_response)
        results = []
        for i in range(n):
            r = copy.deepcopy(sample_response)
            if i:
                r["location_id"] = i
            results.append(r)
        return FakeResponse(results)

    monkeypatch.setattr(http_session.session, "get", fake_get)
    return calls


def test_backfill_uses_archive_with_dates(api, kano):
    extract.fetch_archive([kano], date(2024, 1, 1), date(2024, 12, 31), save_raw=False)
    url, params = api[0]
    assert url == ARCHIVE_URL
    assert params["start_date"] == "2024-01-01"
    assert params["end_date"] == "2024-12-31"
    assert (params["latitude"], params["longitude"]) == ("12.0022", "8.592")


def test_daily_uses_forecast_last_7_complete_days(api, kano):
    extract.fetch_recent([kano], past_days=7, save_raw=False)
    url, params = api[0]
    assert url == FORECAST_URL
    assert params["past_days"] == 7
    assert params["forecast_days"] == 0  # excludes today and the future
    assert "start_date" not in params


def test_several_cities_in_one_request(api, kano):
    results = extract.fetch_recent([kano, ABUJA], save_raw=False)
    assert len(api) == 1  # one request, not one per city
    _, params = api[0]
    assert params["latitude"] == "12.0022,9.05785"
    assert params["longitude"] == "8.592,7.49508"
    assert len(results) == 2


def test_wrong_number_of_results_is_rejected(monkeypatch, kano, sample_response):
    monkeypatch.setattr(http_session.session, "get", lambda *a, **k: FakeResponse(sample_response))
    with pytest.raises(ValueError, match="Asked for 2 locations, got 1"):
        extract.fetch_recent([kano, ABUJA], save_raw=False)


def test_reversed_dates_fail_before_calling_api(api, kano):
    with pytest.raises(ValueError, match="after end_date"):
        extract.fetch_archive([kano], date(2024, 12, 31), date(2024, 1, 1), save_raw=False)
    assert api == []


def test_raw_copy_is_saved_per_city(api, kano, tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "RAW_DIR", tmp_path)
    extract.fetch_recent([kano, ABUJA], save_raw=True)
    assert (tmp_path / "kano-kano-state_2026-11-07_2026-11-11.json").exists()
    assert (tmp_path / "abuja-fct_2026-11-07_2026-11-11.json").exists()


# ---------- the hard deadline ----------

def _trickle_server():
    """A local server that answers one byte every 0.2 s: never silent long enough to time out."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)

    def serve():
        conn, _ = sock.accept()
        conn.recv(1024)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n")
        try:
            for _ in range(1000):
                conn.sendall(b"x")
                time.sleep(0.2)
        except OSError:
            pass
        finally:
            conn.close()
            sock.close()

    threading.Thread(target=serve, daemon=True).start()
    return f"http://127.0.0.1:{sock.getsockname()[1]}/"


def test_deadline_stops_a_trickling_response():
    # A 1 s read timeout never fires (bytes arrive every 0.2 s); the deadline does
    url = _trickle_server()
    start = time.monotonic()
    with pytest.raises(http_session.DeadlineExceeded):
        with http_session.deadline(1.5, "test request"):
            requests.get(url, timeout=(1, 1))
    assert time.monotonic() - start < 3


def test_deadline_does_not_interfere_with_fast_work():
    with http_session.deadline(5, "quick"):
        assert 1 + 1 == 2
