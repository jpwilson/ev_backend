"""The real seed files in catalog/data (whatever exists right now): legacy endpoints
unchanged, loader idempotent, every catalog page answers."""
from conftest import added_rows, canonical, fill_empty_logos, load_seeds, row_counts


def test_real_seed_report(real_db):
    rep = real_db["report"]
    print("loaded:", rep["files_loaded"])
    print("skipped:", [(s["file"], s["reason"]) for s in rep["files_skipped"]])
    assert rep["files_loaded"] or not real_db["files"]


def test_real_legacy_unchanged(real_db):
    cars, makes = added_rows(real_db["env"].engine)
    for path, (code, body) in real_db["before"].items():
        code2, body2 = real_db["after_load"][path]
        assert code2 == code, path
        if code == 200:
            body = fill_empty_logos(path, body, body2)
            assert canonical(path, body2, cars, makes) == canonical(path, body, cars, makes), path


def test_real_loader_idempotent(real_db):
    engine = real_db["env"].engine
    counts = row_counts(engine)
    report = load_seeds(engine, real_db["files"])
    assert report["changes"] == 0, report["stats"]
    assert row_counts(engine) == counts


def test_real_catalog_smoke_every_model(real_db):
    env = real_db["env"]
    for p in ("/catalog/meta", "/catalog/makes", "/catalog/sitemap.xml"):
        assert env.get(p).status_code == 200, p
    makes = env.get("/catalog/makes").json()["makes"]
    for mk in makes:
        assert env.get("/catalog/makes/%s" % mk["slug"]).status_code == 200
    cards = env.get("/catalog/models").json()["models"]
    assert len(cards) == env.get("/catalog/meta").json()["counts"]["models"]
    failures = []
    for card in cards:
        r = env.get("/catalog/models/%s/%s" % (card["make"]["slug"], card["url_slug"]))
        if r.status_code != 200:
            failures.append(card["path"])
            continue
        for g in r.json()["generations"]:
            for v in g["variants"]:
                rv = env.get("/catalog/variants/" + v["key"])
                if rv.status_code != 200:
                    failures.append(v["path"])
    assert not failures, failures[:20]
    for key in ("evs-under-40k", "longest-range-evs", "fastest-evs", "cheapest-evs", "3-row-evs",
                "electric-trucks", "300-mile-range-evs"):
        assert env.get("/catalog/best/" + key).status_code == 200, key
    assert env.get("/catalog/best/nope").status_code == 404


def test_real_every_redirect_resolves(real_db):
    from sqlalchemy import text
    env = real_db["env"]
    with env.engine.connect() as conn:
        paths = [r[0] for r in conn.execute(text("SELECT old_path FROM url_redirects"))]
    kinds = {"/model_detail/": "model", "/manufacturer/": "make", "/car_detail/": "variant"}
    bad = []
    for p in paths:
        prefix = next(k for k in kinds if p.startswith(k))
        r = env.get("/catalog/resolve?kind=%s&key=%s" % (kinds[prefix], p[len(prefix):]))
        if r.status_code != 200:
            bad.append(p)
    assert not bad, bad[:20]
