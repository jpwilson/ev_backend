"""Generated lists (services/catalog_lists.py): ranking rules on a synthetic catalog, the gates, the
registry, and a real-data smoke over every list and the sitemap."""
import re

import services.catalog_lists as L
from catalog_fakes import _check_text, _sitemap, build, model, off, trim, us_suv


def test_list_one_currency_one_cycle_and_exclusions(monkeypatch):
    specs = [
        model("a-one", "a", "suv", [trim("T", [off("UK", None, price=20000, basis="list_incl_vat", rng=400)])],
              markets=("UK",)),
        model("b-one", "b", "suv", [trim("T", [off("UK", None, price=21000, basis="list_incl_vat", rng=500)])],
              markets=("UK",)),
        # launch price only, estimated price, wrong currency, wrong cycle: never ranked
        model("c-one", "c", "suv", [trim("T", [off("UK", None, launch=15000, basis="list_incl_vat", rng=450)])],
              markets=("UK",)),
        model("d-one", "d", "suv", [trim("T", [off("UK", None, price=14000, basis="list_incl_vat", est=True)])],
              markets=("UK",)),
        model("e-one", "e", "suv", [trim("T", [off("UK", None, price=13000, currency="EUR", basis="list_incl_vat",
                                                   rng=300, cycle="CLTC")])], markets=("UK",)),
        model("f-one", "f", "suv", [trim("T", [off("UK", None, price=22000, basis="list_incl_vat", rng=600)],
                                         status="discontinued"),                     # discontinued trim ignored
                                    trim("T2", [off("UK", None, price=25000, basis="list_incl_vat", rng=420)])],
              markets=("UK",)),
        model("g-one", "g", "suv", [trim("T", [off("UK", None, price=19000, basis="list_incl_vat", rng=410)])],
              markets=("UK",), commercial=True),
    ]
    cat = build(specs)
    cheap = L.compute(cat, L.LIST["cheapest-evs-uk"])
    assert [i["model"]["slug"] for i in cheap["items"]] == ["a-one", "b-one", "f-one"]
    assert cheap["excluded"] == 3                                    # c (launch only), d (estimate), e (EUR)
    assert {i["fact"]["currency"] for i in cheap["items"]} == {"GBP"}
    assert cheap["items"][2]["fact"]["value"] == 25000               # not the discontinued trim's price
    rng = L.compute(cat, L.LIST["longest-range-evs-uk"])
    assert [i["model"]["slug"] for i in rng["items"]] == ["b-one", "c-one", "f-one", "a-one"]
    assert {i["fact"]["cycle"] for i in rng["items"]} == {"WLTP"} and rng["excluded"] == 2   # d none, e CLTC
    r = L.response(cat, "cheapest-evs-uk")
    assert r["excluded"]["count"] == 3 and r["excluded"]["reason"].startswith("3 cars on sale in the UK have no")
    assert r["indexable"] is False and "at least 6" in r["reason"]   # gate: fewer than MIN_ITEMS ranked
    assert r["metric"] == "price" and r["ranking"] == "price_asc"
    assert all(i["qualifier"] == "list price including VAT" for i in r["items"])


def _registry(*cfgs):
    out = []
    for c in cfgs:
        base = {"title": c["key"], "h1": c["key"], "blurb": c["key"], "limit": 12}
        base.update(c)
        out.append(base)
    return out


def test_list_gates_ceiling_and_overlap(monkeypatch):
    # 10 cheap cars with short range, 4 dearer cars with long range
    specs = [us_suv("m-c%02d" % i, "m%02d" % i, 20000 + i * 1000, 200 + i) for i in range(10)] + \
            [us_suv("m-d%02d" % i, "n%02d" % i, 36000 + i * 1000, 400 + i) for i in range(4)]
    reg = _registry(
        {"key": "cheap", "market": "US", "metric": "price_asc"},
        {"key": "under-35", "market": "US", "metric": "range_desc", "filters": {"max_price": 35000}},
        {"key": "under-40", "market": "US", "metric": "range_desc", "filters": {"max_price": 40000}},
        {"key": "under-41", "market": "US", "metric": "range_desc", "filters": {"max_price": 41000}},
        {"key": "tiny", "market": "US", "metric": "price_asc", "filters": {"max_price": 23000}},
    )
    monkeypatch.setattr(L, "LISTS", reg)
    monkeypatch.setattr(L, "LIST", {c["key"]: c for c in reg})
    out = L.build_all(build(specs))
    assert out["cheap"]["indexable"]
    assert not out["under-35"]["indexable"] and "overlaps cheap" in out["under-35"]["reason"]   # 10/10 overlap
    assert out["under-40"]["indexable"]                       # 4 dearer cars lead its top 10: 6/10 overlap
    assert not out["under-41"]["indexable"] and "Differs from under-40 by 0" in out["under-41"]["reason"]
    assert not out["tiny"]["indexable"] and "at least 6" in out["tiny"]["reason"]
    assert [r["key"] for r in out["cheap"]["related"]] == ["under-40"]


def test_registry_shape():
    assert len(L.LISTS) <= L.MAX_LISTS
    for key in ("evs-under-40k", "longest-range-evs", "fastest-evs", "cheapest-evs", "3-row-evs",
                "electric-trucks", "300-mile-range-evs"):
        assert key in L.LIST
    assert L.LIST["evs-under-40k"]["metric"] == "range_desc" and L.LIST["300-mile-range-evs"]["metric"] == "price_asc"
    assert not any(c["market"] == "EU" and c["metric"] == "price_asc" for c in L.LISTS)
    for c in L.LISTS:
        assert c["limit"] <= L.MAX_LIMIT
        assert c["key"].endswith({"US": "", "UK": "-uk", "EU": "-europe", "CN": "-china", None: ""}[c["market"]])


# ---------------------------------------------------------------- API

def test_real_every_list(real_db):
    env = real_db["env"]
    reg = env.get("/catalog/lists").json()
    assert reg["count"] == len(L.LISTS) and reg["indexable"] <= L.MAX_LISTS
    for entry in reg["lists"]:
        d = env.get("/catalog/best/" + entry["key"]).json()
        assert d["indexable"] == entry["indexable"] and d["rule"] == entry["rule"]
        assert d["indexable"] == (d["reason"] is not None and d["reason"].endswith("ranked."))
        on_sale = [i for i in d["items"] if i.get("status", "current") == "current"]
        if entry["metric"] in ("price_asc",):
            assert len({i["unit"] for i in on_sale}) <= 1          # one currency
            vals = [i["value"] for i in on_sale]
            assert vals == sorted(vals)
        if entry["metric"] == "range_desc":
            assert len({i["cycle"] for i in on_sale}) <= 1          # one test cycle
            vals = [i["value"] for i in on_sale]
            assert vals == sorted(vals, reverse=True)
        if d["excluded"]["count"]:
            _check_text(d["excluded"]["reason"])
        for s in [d["rule"]] + d["notes"] + d["excluded"]["unknown"]:
            _check_text(s)
        if entry["indexable"] and entry["key"] not in L.ESTABLISHED:
            assert d["ranked"] >= L.MIN_ITEMS
    assert _sitemap(env, "best") == {x["path"] for x in reg["lists"] if x["indexable"]}
    for key in ("evs-under-40k", "longest-range-evs", "fastest-evs", "cheapest-evs", "3-row-evs",
                "electric-trucks", "300-mile-range-evs"):
        r = env.get("/catalog/best/%s?limit=12" % key)
        assert r.status_code == 200 and {"key", "title", "market", "metric", "items", "count"} <= set(r.json())
    print("lists:", reg["count"], "indexable:", reg["indexable"])
