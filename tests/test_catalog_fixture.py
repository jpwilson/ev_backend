"""Migration + loader + API against the snapshot and the test fixtures (deterministic)."""
import pytest

from conftest import (FIXTURE_FILES, _alembic, added_rows, canonical, legacy_snapshot,
                      load_seeds, row_counts)


def _assert_legacy_unchanged(before, after, drop_cars=(), drop_makes=()):
    for path, (code, body) in before.items():
        code2, body2 = after[path]
        assert code2 == code, path
        if code != 200:
            continue
        assert canonical(path, body2, drop_cars, drop_makes) == canonical(path, body, drop_cars, drop_makes), path


def test_catalog_503_before_migration_and_legacy_ok(fixture_db):
    r = fixture_db["meta_before"]
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/json")
    assert "catalog_02_hierarchy" in r.json()["detail"]
    assert all(code in (200, 404) for code, _ in fixture_db["before"].values())
    assert fixture_db["before"]["/cars/cards"][0] == 200


def test_legacy_byte_identical_after_migration(fixture_db):
    # migration alone rewrites no row: bodies must be byte-identical, order included
    assert fixture_db["after_migration"] == fixture_db["before"]


def test_legacy_identical_after_load(fixture_db):
    cars, makes = added_rows(fixture_db["env"].engine)
    assert cars and makes  # the fixtures do add rows
    # /cars/cards only lists representative rows: byte-identical apart from row order
    p = "/cars/cards"
    assert canonical(p, fixture_db["after_load"][p][1]) == canonical(p, fixture_db["before"][p][1])
    _assert_legacy_unchanged(fixture_db["before"], fixture_db["after_load"], cars, makes)


def test_loader_idempotent(fixture_db):
    engine = fixture_db["env"].engine
    counts = row_counts(engine)
    report = load_seeds(engine, FIXTURE_FILES)
    assert report["changes"] == 0, report["stats"]
    assert row_counts(engine) == counts


def test_fixture_report(fixture_db):
    rep = fixture_db["report"]
    assert sorted(rep["files_loaded"]) == ["_example.json", "fisker.json", "tesla.json"]
    assert rep["files_skipped"] == []
    assert rep["merged_legacy"] == {"131": 129}
    assert any("nobody-not-loaded" in w["message"] for w in rep["warnings"])
    assert "Fisker" not in rep["unclaimed_legacy"]


def test_defunct_brand_coerces_statuses(fixture_db):
    env = fixture_db["env"]
    make = env.get("/catalog/makes/fisker").json()
    assert make["make"]["brand_status"] == "defunct" and make["make"]["status_date"] == "2024-06-17"
    groups = {s: [c["slug"] for c in cards] for s, cards in make["models"].items()}
    assert groups["discontinued"] == ["fisker-ocean"]            # stored current
    assert sorted(groups["cancelled"]) == ["fisker-kayak", "fisker-pear", "fisker-ronin"]
    tree = env.get("/catalog/models/fisker/ocean").json()
    assert tree["model"]["own_status"] == "current" and tree["model"]["status"] == "discontinued"
    v = tree["generations"][0]["variants"]
    assert {x["status"] for x in v} == {"discontinued"}
    rel = env.get("/catalog/models/fisker/kayak").json()["relations"]
    assert rel == [{"relation": "predecessor", "model": {
        "slug": "fisker-ocean", "name": "Ocean", "path": "/make/fisker/ocean",
        "make": rel[0]["model"]["make"], "status": "discontinued"}}]


def test_generations_newest_first_and_images(fixture_db):
    env = fixture_db["env"]
    tree = env.get("/catalog/models/tesla/model-3").json()
    assert [g["slug"] for g in tree["generations"]] == ["2024", "2017"]
    assert tree["default_generation"] == "2024" and tree["generations"][0]["is_default"]
    assert tree["generations"][0]["images"] == []                 # unverified image never served
    assert tree["generations"][1]["images"][0]["url"].endswith("tes_m3_lng_range.png")
    card = next(c for c in env.get("/catalog/models?make=tesla").json()["models"])
    assert card["image"] is None                                  # never another generation's photo
    assert card["from_price"]["value"] == 42490 and card["from_price"]["variant"]["slug"] == "rwd"
    assert card["max_range"] == {"value": 363, "unit": "mi", "cycle": "EPA", "market": "US",
                                 "model_year": 2025, "is_estimate": False,
                                 "variant": card["max_range"]["variant"]}
    eu = env.get("/catalog/models?make=tesla&market=EU").json()["models"][0]
    assert eu["max_range"]["cycle"] == "WLTP" and eu["from_price"]["currency"] == "EUR"


def test_resolve_legacy_urls(fixture_db):
    env = fixture_db["env"]
    r = env.get("/catalog/resolve?kind=variant&key=131").json()
    assert r["path"] == "/make/fisker/ocean/2023/extreme" and r["reason"] == "merge"
    assert env.get("/catalog/resolve?kind=variant&key=204").json()["path"] == "/make/tesla/model-3/2024/rwd"
    assert env.get("/catalog/resolve?kind=model&key=Tesla-Model-3").json()["path"] == "/make/tesla/model-3"
    assert env.get("/catalog/resolve?kind=make&key=fisker").json()["path"] == "/make/fisker"
    assert env.get("/catalog/resolve?kind=make&key=example-motors").json()["path"] == "/make/example-motors"
    assert env.get("/catalog/resolve?kind=variant&key=99999").status_code == 404
    assert env.get("/catalog/resolve?kind=bogus&key=x").status_code == 400


def test_downgrade_roundtrip(fixture_db):
    """Runs last: downgrade restores the legacy responses exactly, upgrade + load again works."""
    env = fixture_db["env"]
    _alembic(env.url, "downgrade", "a3f8b2c1d4e5")
    after_down = legacy_snapshot(env)
    for path, (code, body) in fixture_db["before"].items():
        assert after_down[path][0] == code
        if code == 200:
            assert canonical(path, after_down[path][1]) == canonical(path, body), path
    assert env.get("/catalog/meta").status_code == 503
    _alembic(env.url, "upgrade", "head")
    load_seeds(env.engine, FIXTURE_FILES)
    assert env.get("/catalog/models/tesla/model-3").status_code == 200
