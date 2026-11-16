"""Manage the cities the pipeline tracks (the dim_city table).

    python -m src.cities list [--all]
    python -m src.cities search Ilorin
    python -m src.cities add Ilorin [--state Kwara] [--pick N] [--backfill-from 2024-01-01]
    python -m src.cities deactivate "Ilorin"     # stop fetching, keep history
    python -m src.cities activate "Ilorin, Kwara"
"""
import argparse
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, text

from src.config import COUNTRY_CODE, GEOCODING_URL, HTTP_TIMEOUT_S, REQUEST_DEADLINE_S
from src.http_session import deadline, session

logger = logging.getLogger(__name__)

# GeoNames feature codes for a capital or administrative seat: national capital,
# state capital, local government area seat. Used to pick "the" Ibadan over villages.
ADMIN_SEATS = {"PPLC", "PPLA", "PPLA2"}


@dataclass(frozen=True)
class City:
    city_id: int
    name: str
    state: str
    latitude: float
    longitude: float
    active: bool = True

    @property
    def label(self) -> str:
        return f"{self.name} ({self.state})"

    @property
    def slug(self) -> str:
        """Filesystem-safe id, e.g. 'port-harcourt-rivers-state'."""
        return re.sub(r"[^a-z0-9]+", "-", f"{self.name} {self.state}".lower()).strip("-")


# ---------- reading dim_city ----------

def list_cities(conn: Connection, include_inactive: bool = False) -> list[City]:
    rows = conn.execute(text("""
        SELECT city_id, name, state, latitude, longitude, active
        FROM dim_city
        WHERE active OR :include_inactive
        ORDER BY name, state
    """), {"include_inactive": include_inactive})
    return [
        City(r.city_id, r.name, r.state, float(r.latitude), float(r.longitude), r.active)
        for r in rows
    ]


def resolve(cities: list[City], wanted: list[str]) -> list[City]:
    """Match names like 'Kano' or 'Ibadan, Oyo' against tracked cities.

    Raises ValueError for a name that matches nothing or more than one city.
    """
    chosen = []
    for item in wanted:
        name, _, state = (part.strip().lower() for part in item.partition(","))
        matches = [c for c in cities
                   if c.name.lower() == name and state in c.state.lower()]
        if not matches:
            raise ValueError(f"{item!r} isn't tracked. Add it with: python -m src.cities add {name.title()!r}")
        if len(matches) > 1:
            options = ", ".join(f"'{c.name}, {c.state}'" for c in matches)
            raise ValueError(f"{item!r} matches several cities; use one of: {options}")
        chosen.append(matches[0])
    return chosen


# ---------- geocoding ----------

class AmbiguousPlace(Exception):
    def __init__(self, candidates: list[dict]):
        self.candidates = candidates
        super().__init__(f"{len(candidates)} places match")


def search_places(name: str) -> list[dict]:
    """Populated places in Nigeria matching `name`, most relevant first."""
    with deadline(REQUEST_DEADLINE_S, f"geocoding {name!r}"):
        resp = session.get(GEOCODING_URL, params={
            "name": name, "count": 20, "country_code": COUNTRY_CODE,
            "language": "en", "format": "json",
        }, timeout=HTTP_TIMEOUT_S)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    # The API treats country_code as a hint, not a filter, and returns airports
    # and districts too, so keep only towns and cities in Nigeria.
    return [
        r for r in results
        if r.get("country_code") == COUNTRY_CODE
        and r.get("feature_code", "").startswith("PPL")
        and r.get("admin1")
    ]


def choose_place(candidates: list[dict], name: str,
                 state: str | None = None, pick: int | None = None) -> dict:
    """Pick one place, or raise AmbiguousPlace so the user can narrow it down."""
    if state:
        candidates = [c for c in candidates if state.lower() in c["admin1"].lower()]
    exact = [c for c in candidates if c["name"].lower() == name.lower()]
    candidates = exact or candidates

    if not candidates:
        where = f" in {state}" if state else ""
        raise LookupError(f"No town or city called {name!r} found{where}")
    if pick is not None:
        if not 1 <= pick <= len(candidates):
            raise ValueError(f"--pick must be between 1 and {len(candidates)}")
        return candidates[pick - 1]
    if len(candidates) == 1:
        return candidates[0]

    # Several matches: if exactly one is a capital/admin seat, that's the one people mean
    seats = [c for c in candidates if c.get("feature_code") in ADMIN_SEATS]
    if len(seats) == 1:
        return seats[0]
    raise AmbiguousPlace(candidates)


def describe(place: dict) -> str:
    parts = [place["name"], place["admin1"]]
    if place.get("admin2"):
        parts.insert(1, place["admin2"])
    pop = f", pop. {place['population']:,}" if place.get("population") else ""
    return f"{', '.join(parts)} ({place['latitude']:.4f}, {place['longitude']:.4f}{pop})"


# ---------- writing dim_city ----------

def add_city(conn: Connection, place: dict) -> tuple[City, bool]:
    """Insert a geocoded place; return (city, created). Re-activates it if it already exists."""
    row = conn.execute(text("""
        INSERT INTO dim_city (name, state, latitude, longitude)
        VALUES (:name, :state, :latitude, :longitude)
        ON CONFLICT (name, state) DO NOTHING
        RETURNING city_id
    """), {"name": place["name"], "state": place["admin1"],
           "latitude": place["latitude"], "longitude": place["longitude"]}).first()
    created = row is not None
    if not created:
        # Already tracked: keep its coordinates (its history was fetched with them)
        conn.execute(text("UPDATE dim_city SET active = true WHERE name = :name AND state = :state"),
                     {"name": place["name"], "state": place["admin1"]})

    city = next(c for c in list_cities(conn)
                if c.name == place["name"] and c.state == place["admin1"])
    return city, created


def set_active(conn: Connection, city: City, active: bool) -> None:
    conn.execute(text("UPDATE dim_city SET active = :active WHERE city_id = :id"),
                 {"active": active, "id": city.city_id})


# ---------- command line ----------

def _cmd_list(conn: Connection, args) -> int:
    cities = list_cities(conn, include_inactive=args.all)
    for c in cities:
        status = "" if c.active else "  [inactive]"
        print(f"{c.city_id:>5}  {c.name:<20} {c.state:<25} {c.latitude:>9.4f} {c.longitude:>9.4f}{status}")
    print(f"{len(cities)} cities")
    return 0


def _cmd_search(_conn, args) -> int:
    places = search_places(args.name)
    if not places:
        print(f"No towns or cities called {args.name!r} found in Nigeria")
        return 1
    for i, p in enumerate(places, 1):
        print(f"{i:>3}. {describe(p)}  [{p.get('feature_code')}]")
    return 0


def _cmd_add(conn: Connection, args) -> int:
    places = search_places(args.name)
    try:
        place = choose_place(places, args.name, args.state, args.pick)
    except AmbiguousPlace as e:
        print(f"{args.name!r} matches several places. Re-run with --state or --pick N:")
        for i, p in enumerate(e.candidates, 1):
            print(f"{i:>3}. {describe(p)}  [{p.get('feature_code')}]")
        return 1
    except (LookupError, ValueError) as e:
        print(e)
        return 1

    city, created = add_city(conn, place)
    if created:
        print(f"Added: {describe(place)}")
    else:
        print(f"Already tracked (now active): {city.label} "
              f"({city.latitude:.4f}, {city.longitude:.4f}), city_id {city.city_id}")
    others = [p for p in places if p is not place and p["name"].lower() == args.name.lower()]
    if others:
        n = len(others)
        print(f"  ({n} other place{'s' if n > 1 else ''} share{'' if n > 1 else 's'} this name; "
              "use --state or --pick to choose another)")
    args.added_city = city
    return 0


def _cmd_set_active(conn: Connection, args, active: bool) -> int:
    try:
        [city] = resolve(list_cities(conn, include_inactive=True), [args.city])
    except ValueError as e:
        print(e)
        return 1
    set_active(conn, city, active)
    print(f"{city.label} is now {'active' if active else 'inactive'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Manage tracked cities (dim_city).")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show tracked cities")
    p.add_argument("--all", action="store_true", help="include inactive cities")

    p = sub.add_parser("search", help="look up a place without adding it")
    p.add_argument("name")

    p = sub.add_parser("add", help="geocode a place and start tracking it")
    p.add_argument("name")
    p.add_argument("--state", help="narrow to a state, e.g. Kwara")
    p.add_argument("--pick", type=int, help="choose result N from the list shown")
    p.add_argument("--backfill-from", type=date.fromisoformat, metavar="YYYY-MM-DD",
                   help="also load history from this date to yesterday")

    for name in ("deactivate", "activate"):
        p = sub.add_parser(name, help=f"{name} a tracked city")
        p.add_argument("city", help="'Name' or 'Name, State'")

    args = parser.parse_args(argv)
    if args.command == "search":  # needs no database
        return _cmd_search(None, args)

    # Imported here to avoid a circular import (pipeline imports this module)
    from src.load import get_engine
    from src.pipeline import run, yesterday

    with get_engine().begin() as conn:
        if args.command == "list":
            code = _cmd_list(conn, args)
        elif args.command == "add":
            code = _cmd_add(conn, args)
        else:
            code = _cmd_set_active(conn, args, active=args.command == "activate")

    if code != 0 or args.command != "add":
        return code

    city = args.added_city
    if args.backfill_from:
        # The city is committed above, so the normal pipeline can load it
        failed = run("backfill", [city], args.backfill_from, yesterday())
        return 1 if failed else 0
    print("Load its history with:\n  python -m src.pipeline --mode backfill "
          f"--start 2024-01-01 --end {yesterday()} --cities \"{city.name}, {city.state}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
