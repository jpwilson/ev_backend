"""Press photos stored on the site and make logos: validator rules, loader writes, API output."""
import copy
import json
import os

import pytest
from sqlalchemy import text

from conftest import BACKEND

import validate_seed

PRESS_PATH = "/pub_assets/car_images/catalog/fisker-ocean-2023-side.jpg"
LOGO_PATH = "/pub_assets/logos/fisker.svg"
FISKER = os.path.join(BACKEND, "tests", "fixtures", "catalog", "fisker.json")


def _public(tmp_path, svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'):
    pub = tmp_path / "public"
    (pub / "pub_assets" / "car_images" / "catalog").mkdir(parents=True)
    (pub / "pub_assets" / "logos").mkdir(parents=True)
    (pub / PRESS_PATH.lstrip("/")).write_bytes(b"\xff\xd8\xff")
    (pub / LOGO_PATH.lstrip("/")).write_text(svg)
    (pub / "pub_assets" / "logos" / "fisker.png").write_bytes(b"\x89PNG")
    return str(pub)


def _fisker():
    with open(FISKER, encoding="utf-8") as fh:
        return json.load(fh)


def _press(**over):
    im = {"source": "press", "file_url": PRESS_PATH,
          "page_url": "https://example.com/test-fixture/press/ocean", "credit": "Fisker press photo",
          "license": "Manufacturer press photo, editorial use", "view": "side",
          "verified_by_viewing": True}
    im.update(over)
    return im


def _logo(**over):
    lg = {"file_url": LOGO_PATH, "page_url": "https://example.com/test-fixture/brand",
          "credit": "Fisker", "license": None}
    lg.update(over)
    return lg


def _check(doc, public_dir):
    rep = validate_seed.Report()
    validate_seed.FileCheck(rep, "fisker.json", public_dir).run(doc)
    return ([(e["path"], e["message"]) for e in rep.errors],
            [(w["path"], w["message"]) for w in rep.warnings])


def _with(press=None, logo=None):
    doc = _fisker()
    if press is not None:
        doc["models"][0]["generations"][0]["images"].append(press)
    if logo is not None:
        doc["make"]["logo"] = logo
    return doc


IMG = "$.models[0].generations[0].images[1]"


# ------------------------------------------------------------------ validator

def test_press_site_path_accepted(tmp_path):
    errs, _ = _check(_with(press=_press(), logo=_logo()), _public(tmp_path))
    assert errs == []
    # license may be null; https press URLs still work as before
    errs, _ = _check(_with(press=_press(license=None)), _public(tmp_path / "b"))
    assert errs == []
    errs, _ = _check(_with(press=_press(file_url="https://media.example.com/ocean.jpg")), None)
    assert errs == []


@pytest.mark.parametrize("over, where", [
    ({"page_url": None}, ".page_url"),
    ({"credit": None}, ".credit"),
    ({"file_url": "/pub_assets/car_images/catalog/missing.jpg"}, ".file_url"),
    ({"file_url": "/pub_assets/car_images/fisker_ocean_extreme.png"}, ".file_url"),   # not under catalog/
    ({"file_url": "/pub_assets/car_images/catalog/../hero.jpg"}, ".file_url"),
    ({"file_url": "/pub_assets/car_images/catalog/ocean.gif"}, ".file_url"),
    ({"file_url": "pub_assets/car_images/catalog/ocean.jpg"}, ".file_url"),             # not a site path
])
def test_press_site_path_rejected(tmp_path, over, where):
    errs, _ = _check(_with(press=_press(**over)), _public(tmp_path))
    assert any(p == IMG + where for p, _ in errs), errs


def test_site_files_not_checked_without_public_dir(tmp_path):
    missing = str(tmp_path / "no-such-public")
    doc = _with(press=_press(file_url="/pub_assets/car_images/catalog/elsewhere.jpg"),
                logo=_logo(file_url="/pub_assets/logos/fisker.png"))
    assert _check(doc, missing)[0] == []
    # shape rules still apply
    errs, _ = _check(_with(press=_press(file_url="/pub_assets/elsewhere.jpg")), missing)
    assert [p for p, _ in errs] == [IMG + ".file_url"]


def test_logo_accepted(tmp_path):
    pub = _public(tmp_path)
    for lg in (_logo(), _logo(file_url="/pub_assets/logos/fisker.png", credit=None),
               _logo(file_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/Fisker_logo.svg",
                     license="Public domain")):
        errs, warns = _check(_with(logo=lg), pub)
        assert errs == [] and not any(p.startswith("$.make.logo") for p, _ in warns), (lg, errs, warns)
    assert _check(_with(logo=None), pub)[0] == []      # null logo = no logo


@pytest.mark.parametrize("lg, where", [
    (_logo(page_url=None), "$.make.logo.page_url"),
    ({"file_url": LOGO_PATH, "credit": None}, "$.make.logo"),                       # page_url missing
    (_logo(file_url="http://example.com/fisker.svg"), "$.make.logo.file_url"),     # https only
    (_logo(file_url="/pub_assets/makes/fisker_logo.png"), "$.make.logo.file_url"),  # not under logos/
    (_logo(file_url="/pub_assets/logos/fisker.jpg"), "$.make.logo.file_url"),
    (_logo(file_url="/pub_assets/logos/missing.svg"), "$.make.logo.file_url"),
    (_logo(alt="x"), "$.make.logo.alt"),                                            # unknown key
    ("/pub_assets/logos/fisker.svg", "$.make.logo"),                                 # not an object
])
def test_logo_rejected(tmp_path, lg, where):
    errs, _ = _check(_with(logo=lg), _public(tmp_path))
    assert any(p == where for p, _ in errs), errs


def test_logo_warnings(tmp_path):
    pub = _public(tmp_path, svg='<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')
    os.rename(os.path.join(pub, "pub_assets", "logos", "fisker.png"),
              os.path.join(pub, "pub_assets", "logos", "fisker-inc.png"))
    _, warns = _check(_with(logo=_logo()), pub)
    assert any("viewBox" in m for _, m in warns)
    errs, warns = _check(_with(logo=_logo(file_url="/pub_assets/logos/fisker-inc.png")), pub)
    assert errs == [] and any("does not match make slug" in m for _, m in warns)


# ------------------------------------------------------------------ loader + API

def _load(conn, doc, tmp_path, name):
    import load_seed
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return load_seed.run(conn, [str(p)])


def _logo_of(conn, slug):
    return conn.execute(text("SELECT lrg_logo_img_url FROM makes WHERE slug = :s"), {"s": slug}).scalar()


def test_loader_fills_empty_logo_only_and_serves_site_paths(fixture_db, tmp_path, monkeypatch):
    import services.catalog_service as svc
    monkeypatch.setattr(validate_seed, "PUBLIC_DIR", _public(tmp_path))
    engine = fixture_db["env"].engine
    doc = _with(press=_press(), logo=_logo())
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # an existing logo is never replaced
            before = _logo_of(conn, "fisker")
            assert before
            rep = _load(conn, doc, tmp_path, "fisker.json")
            assert rep["files_skipped"] == [], rep["files_skipped"]
            assert _logo_of(conn, "fisker") == before

            # an empty one is filled, once
            conn.execute(text("UPDATE makes SET lrg_logo_img_url = '' WHERE slug = 'fisker'"))
            rep = _load(conn, doc, tmp_path, "fisker.json")
            assert _logo_of(conn, "fisker") == LOGO_PATH
            assert rep["stats"]["makes"].get("updated") == 1
            rep = _load(conn, doc, tmp_path, "fisker.json")
            assert rep["changes"] == 0, rep["stats"]

            # a later, different seed logo does not replace the filled one
            doc2 = copy.deepcopy(doc)
            doc2["make"]["logo"]["file_url"] = "/pub_assets/logos/fisker.png"
            rep = _load(conn, doc2, tmp_path, "fisker.json")
            assert rep["changes"] == 0 and _logo_of(conn, "fisker") == LOGO_PATH

            # NULL counts as empty too
            conn.execute(text("UPDATE makes SET lrg_logo_img_url = NULL WHERE slug = 'fisker'"))
            _load(conn, doc2, tmp_path, "fisker.json")
            assert _logo_of(conn, "fisker") == "/pub_assets/logos/fisker.png"

            # the API passes both site paths through unchanged
            cat = svc.Catalog(conn, make_slug="fisker")
            make = next(iter(cat.makes.values()))
            assert cat.make_full(make)["logo_url"] == "/pub_assets/logos/fisker.png"
            cat = svc.Catalog(conn, model_key=("fisker", "ocean"))
            tree = cat.model_tree(next(iter(cat.models.values())))
            imgs = tree["generations"][0]["images"]
            press = [im for im in imgs if im["source"] == "press"]
            assert press == [dict(press[0], url=PRESS_PATH, credit="Fisker press photo",
                                  page_url="https://example.com/test-fixture/press/ocean",
                                  license="Manufacturer press photo, editorial use", is_primary=False)]
            # the front three-quarter legacy photo stays primary
            assert [im["url"] for im in imgs if im["is_primary"]] == \
                ["/pub_assets/car_images/fisker_ocean_extreme.png"]
        finally:
            trans.rollback()


def test_new_make_gets_seed_logo(fixture_db):
    make = fixture_db["env"].get("/catalog/makes/example-motors").json()["make"]
    assert make["logo_url"] == \
        "https://upload.wikimedia.org/wikipedia/commons/x/xx/Example_Motors_logo.svg"
