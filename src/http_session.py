"""One shared HTTP session for every Open-Meteo call (weather and geocoding)."""
import signal
import threading
from contextlib import contextmanager

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


class DeadlineExceeded(Exception):
    """Raised when a request (with all its retries) runs past its hard deadline.

    Deliberately not a TimeoutError/OSError: urllib3 catches those and would retry.
    """


@contextmanager
def deadline(seconds: float, what: str):
    """Abort the block if it takes longer than `seconds` in total.

    requests' `timeout` only limits the silence between bytes: a server that sends a
    byte every few seconds can keep a request open forever. (It held a GitHub Actions
    run for 30 minutes.) This uses a SIGALRM timer, so it only works on Unix in the
    main thread; anywhere else it does nothing and the per-read timeout still applies.
    """
    if not hasattr(signal, "SIGALRM") or threading.current_thread() is not threading.main_thread():
        yield
        return

    def on_alarm(signum, frame):
        raise DeadlineExceeded(f"{what} took longer than {seconds:g}s")

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
