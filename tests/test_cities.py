import pytest
from sqlalchemy import text

from src import cities, http_session
from src.cities import AmbiguousPlace, City, add_city, choose_place, list_cities, resolve


def place(name, state, code="PPL", pop=None, country="NG", lat=7.0, lon=4.0, admin2=None):
    return {"name": name, "admin1": state, "admin2": admin2, "feature_code": code,
            "population": pop, "country_code": country, "latitude": lat, "longitude": lon}


# Shaped like the real geocoder results for "Ibadan" (one city, several villages)
IBADAN = [
    place("Ibadan", "Oyo State", "PPLA", 3_649_000, lat=7.37756, lon=3.90591),
    place("Ibadan", "Niger State"),
    place("Ibadan", "Borno State"),
    place("Ibadan", "Ogun State"),
]


# ---------- choose_place: picking one geocoder result ----------

def test_single_admin_seat_is_chosen_over_villages():
    assert choose_place(IBADAN, "Ibadan")["admin1"] == "Oyo State"


def test_state_narrows_the_choice():
    assert choose_place(IBADAN, "Ibadan", state="ogun")["admin1"] == "Ogun State"


def test_pick_chooses_by_position():
    assert choose_place(IBADAN, "Ibadan", pick=3)["admin1"] == "Borno State"


def test_several_villages_and_no_seat_is_ambiguous():
    villages = [place("Ikire", "Osun State"), place("Ikire", "Oyo State")]
    with pytest.raises(AmbiguousPlace) as e:
        choose_place(villages, "Ikire")
    assert len(e.value.candidates) == 2


def test_exact_name_beats_partial_match():
    results = [place("Port Harcourtgbene", "Bayelsa State"),
               place("Port Harcourt", "Rivers State", "PPLA")]
    assert choose_place(results, "Port Harcourt")["name"] == "Port Harcourt"


def test_no_match_raises():
    with pytest.raises(LookupError):
        choose_place(IBADAN, "Ibadan", state="Lagos")


def test_pick_out_of_range_raises():
    with pytest.raises(ValueError):
        choose_place(IBADAN, "Ibadan", pick=9)


# ---------- search_places: filtering the API response ----------

def test_search_keeps_only_nigerian_towns(monkeypatch):
    raw = [
        place("Kano", "Kano State", "PPLA", 4_910_000),
        place("Kanoya", "Kagoshima", "PPLA2", country="JP"),   # wrong country
        place("Kano Airport", "Kano State", "AIRP"),             # not a town
    ]

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"results": raw}

    monkeypatch.setattr(http_session.session, "get", lambda *a, **k: Resp())
    assert [p["name"] for p in cities.search_places("Kano")] == ["Kano"]


# ---------- resolve: matching --cities arguments ----------

TRACKED = [
    City(1, "Ibadan", "Oyo State", 7.4, 3.9),
    City(2, "Ibadan", "Ogun State", 7.3, 3.5),
    City(3, "Kano", "Kano State", 12.0, 8.6),
]


def test_resolve_by_name():
    assert resolve(TRACKED, ["kano"]) == [TRACKED[2]]


def test_resolve_by_name_and_state():
    assert resolve(TRACKED, ["Ibadan, Ogun"]) == [TRACKED[1]]


def test_resolve_ambiguous_name_asks_for_state():
    with pytest.raises(ValueError, match="several cities"):
        resolve(TRACKED, ["Ibadan"])


def test_resolve_unknown_city_suggests_adding_it():
    with pytest.raises(ValueError, match="src.cities add"):
        resolve(TRACKED, ["Ilorin"])


def test_slug_is_filesystem_safe():
    assert City(1, "Port Harcourt", "Rivers State", 4.8, 7.0).slug == "port-harcourt-rivers-state"


# ---------- add_city: writing dim_city (rolled back) ----------

def test_add_city_inserts_then_recognises_duplicate(conn):
    # A made-up place, so the test doesn't depend on which real cities are tracked
    ilorin = place("Testtown", "Alpha State", "PPLA", lat=8.5, lon=4.5)
    city, created = add_city(conn, ilorin)
    assert created and city.label == "Testtown (Alpha State)"

    again, created = add_city(conn, ilorin)
    assert not created and again.city_id == city.city_id


def test_add_city_reactivates_inactive_city(conn):
    city, _ = add_city(conn, place("Testtown", "Alpha State", "PPLA"))
    cities.set_active(conn, city, False)
    assert city not in list_cities(conn)

    again, created = add_city(conn, place("Testtown", "Alpha State", "PPLA"))
    assert not created and again.active


def test_same_name_in_another_state_is_a_different_city(conn):
    a, _ = add_city(conn, place("Testtown", "Alpha State", "PPLA"))
    b, created = add_city(conn, place("Testtown", "Beta State"))
    assert created and a.city_id != b.city_id
    count = conn.execute(text("SELECT COUNT(*) FROM dim_city WHERE name = 'Testtown'")).scalar_one()
    assert count == 2
