"""Model comparisons (services/catalog_compare.py): pair selection rules on a synthetic catalog, the
fixture DB endpoints, and a real-data smoke over every selected pair and the sitemap."""
import re
from collections import defaultdict

import services.catalog_compare as CP
import services.catalog_lists as L
from catalog_fakes import BANNED, _check_text, _sitemap, names_in, build, model, off, trim, us_suv



CATALOG = [
    us_suv("acme-alpha", "acme", 40000, 300, dc=150, accel=5.0),
    us_suv("acme-beta", "acme", 42000, 310, dc=150, accel=5.5, body="sedan"),
    us_suv("acme-gamma", "acme", 90000, 400, dc=250, accel=3.0, body="pickup"),
    us_suv("bolt-one", "bolt", 41000, 280, dc=120, accel=6.0),
    us_suv("bolt-two", "bolt", 43000, 260, dc=100, accel=6.5),
    us_suv("crux-one", "crux", 44000, 320, dc=200, accel=4.5),
    us_suv("crux-far", "crux", 90000, 330, dc=200, accel=4.5),       # outside the 1.3 price ratio of the SUVs
    us_suv("dyna-van", "dyna", 41000, 250, dc=100, commercial=True),  # commercial: never selected
    us_suv("ghost-one", "ghost", 41000, 250, dc=100, make_status="defunct"),
    model("echo-one", "echo", "suv", [trim("Base", [off(price=40500)])]),   # no range: no rival pairs
]


# ---------------------------------------------------------------- selection

def test_selection_is_deterministic_canonical_and_unique(monkeypatch):
    import routers.seo
    monkeypatch.setattr(routers.seo, "COMPARE_PAIRS", [])
    keys = None
    for seed in (1, 2, 3):
        idx = CP.build_index(build(CATALOG, relations=[("bolt-one", "acme-alpha", "twin"),
                                                        ("acme-alpha", "bolt-one", "twin")], shuffle=seed))
        got = [(p["key"], p["source"], p["indexable"]) for p in idx["pairs"]]
        assert keys is None or got == keys
        keys = got
    ks = [k for k, _, _ in keys]
    assert len(ks) == len(set(ks))                                   # no duplicate pairs
    for k in ks:
        a, b = k.split("-vs-")
        assert a < b                                                 # canonical order
    srcs = dict((k, s) for k, s, _ in keys)
    assert srcs["acme-alpha-vs-bolt-one"] == "twin"                  # two-way twin rows -> one pair, relation first
    assert srcs["acme-alpha-vs-acme-beta"] == "same_make"
    assert not any("dyna-van" in k or "ghost-one" in k for k in ks)  # commercial, defunct brand
    assert not any("echo-one" in k for k in ks)                      # no range -> not a rival
    assert "crux-far-vs-crux-one" not in ks                          # same make, same body: not a same-make pair
    assert not any(k in ks for k in ("acme-alpha-vs-crux-far", "bolt-one-vs-crux-far"))   # price ratio > 1.3
    order = [s for _, s, _ in keys]
    assert order == sorted(order, key=CP.SOURCES.index)              # priority order


def test_same_make_cap_and_rivals_per_model(monkeypatch):
    import routers.seo
    monkeypatch.setattr(routers.seo, "COMPARE_PAIRS", [])
    specs = [us_suv("zed-s%d" % i, "zed", 40000 + i * 500, 300, body="sedan") for i in range(4)] + \
            [us_suv("zed-x", "zed", 40100, 300)] + \
            [us_suv("%s-x" % mk, mk, 40000 + i * 300, 300) for i, mk in enumerate("abcdefg")]
    idx = CP.build_index(build(specs))
    same = [p for p in idx["pairs"] if p["source"] == "same_make"]
    assert sum(1 for p in same if "zed-x" in p["key"]) <= CP.SAME_MAKE_PER_MODEL
    # every rival pair is among one of its models' RIVALS_PER_MODEL nearest same-body other-make models
    rivals = [p for p in idx["pairs"] if p["source"] == "rival"]
    assert rivals and all(p["a"]["body_style"] == p["b"]["body_style"] and p["a"]["make_id"] != p["b"]["make_id"]
                          for p in rivals)
    per = defaultdict(int)
    for p in rivals:
        per[p["a"]["slug"]] += 1
        per[p["b"]["slug"]] += 1
    n_suvs = 8
    assert len(rivals) <= n_suvs * CP.RIVALS_PER_MODEL


def test_pinned_exempt_and_cap(monkeypatch):
    import routers.seo
    specs = CATALOG + [model("pin-a", "pin", "suv", [trim("Base")]), model("pin-b", "qin", "suv", [trim("Base")])]
    monkeypatch.setattr(routers.seo, "COMPARE_PAIRS", ["pin-b-vs-pin-a", "pin-a-vs-nope"])
    monkeypatch.setattr(CP, "MAX_INDEXED_PAIRS", 3)
    idx = CP.build_index(build(specs))
    first = idx["pairs"][0]
    assert first["key"] == "pin-a-vs-pin-b" and first["source"] == "pinned"
    assert first["indexable"] and first["quality"]["comparable_facts"] == 0   # exempt from the facts rule
    assert "pin-a-vs-nope" not in idx["by_key"]
    assert sum(p["indexable"] for p in idx["pairs"]) == 3 == idx["indexed"]
    capped = [p for p in idx["pairs"] if not p["indexable"] and "cap" in p["reason"]]
    assert capped
    for p in idx["pairs"]:
        if p["indexable"] and p["source"] != "pinned":
            q = p["quality"]
            assert q["comparable_facts"] >= CP.MIN_COMPARABLE_FACTS and q["has_price"] and q["has_range"]


# ---------------------------------------------------------------- page

def _page(cat, a, b, market=None):
    s = CP.by_slug(cat)
    return CP.page(cat, s[a], s[b], market)


def test_rows_never_compare_across_groups_and_highlight(monkeypatch):
    import routers.seo
    monkeypatch.setattr(routers.seo, "COMPARE_PAIRS", [])
    specs = [
        model("acme-a", "acme", "suv", [trim("A1", [off(price=40000, basis="msrp_incl_destination", rng=300),
                                                     off("UK", None, price=30000, basis="list_incl_vat", rng=480)],
                                               dc_kw=150, accel_0_60_s=5.0)], markets=("US", "UK")),
        model("bolt-b", "bolt", "suv", [trim("B1", [off(price=41000, rng=320),
                                                     off("UK", None, price=31000, basis="list_incl_vat", rng=500)],
                                               dc_kw=200, accel_0_60_s=4.0)], markets=("US", "UK")),
    ]
    cat = build(specs)
    d = _page(cat, "bolt-b", "acme-a")                    # reversed input -> canonical path
    assert d["path"] == "/compare/acme-a-vs-bolt-b" and d["market"] == "US" and d["markets"] == ["US", "UK"]
    rows = {r["key"]: r for r in d["rows"]}
    price = rows["entry_price"]
    assert price["compare"]["status"] == "not_comparable" and price["compare"]["delta"] is None
    assert price["highlight"] is None
    assert not any("cheaper" in f["q"] for f in d["faq"])     # basis differs: no "which is cheaper"
    rng = rows["longest_range"]
    assert rng["compare"]["status"] == "b_higher" and rng["compare"]["delta"] == 20 and rng["highlight"] == "b"
    assert rows["quickest_0_60"]["highlight"] == "b" and rows["fastest_dc"]["highlight"] == "b"
    for r in d["rows"]:
        if r["compare"]["status"] in ("a_higher", "b_higher", "equal") and r["kind"] == "number":
            a, b = r["a"], r["b"]
            assert (a["unit"], a["cycle"], a["market"], a["basis"]) == (b["unit"], b["cycle"], b["market"], b["basis"])
    uk = _page(cat, "acme-a", "bolt-b", "UK")
    rows = {r["key"]: r for r in uk["rows"]}
    assert rows["entry_price"]["compare"]["status"] == "b_higher" and rows["entry_price"]["highlight"] == "a"
    assert rows["entry_price"]["a"]["unit"] == "GBP" and rows["longest_range"]["a"]["cycle"] == "WLTP"
    faq = {f["q"]: f["a"] for f in uk["faq"]}
    q = "Which is cheaper, the Acme A or the Bolt B?"
    assert faq[q].startswith("The Acme A has the lower entry price")      # winner is the lower price
    for s in d["summary"] + uk["summary"] + [f["q"] + " " + f["a"] for f in d["faq"] + uk["faq"]]:
        assert not BANNED.search(s), s
    assert d["quality"]["source"] == "rival" and d["indexable"] is True    # 3 comparable: range, 0-60, DC
    assert d["more"] == {"a": [], "b": []}                                  # no other indexable pair


# ---------------------------------------------------------------- API

def test_fixture_compare_endpoints(fixture_db):
    env = fixture_db["env"]
    r = env.get("/catalog/compare/tesla-model-3/fisker-ocean")
    assert r.status_code == 200
    d = r.json()
    assert d["path"] == "/compare/fisker-ocean-vs-tesla-model-3" and d["indexable"] is False
    assert env.get("/catalog/compare/fisker-ocean/tesla-model-3").json()["path"] == d["path"]
    assert env.get("/catalog/compare/tesla-model-3/tesla-model-3").status_code == 404
    assert env.get("/catalog/compare/tesla-model-3/nope").status_code == 404
    assert env.get("/catalog/compare/tesla-model-3/fisker-ocean?market=JP").status_code == 400
    pairs = env.get("/catalog/compare-pairs").json()
    assert pairs["cap"] == CP.MAX_INDEXED_PAIRS and pairs["count"] == len(pairs["pairs"])
    assert _sitemap(env, "compare") == {p["path"] for p in pairs["pairs"] if p["indexable"]}
    lists = env.get("/catalog/lists").json()
    assert lists["count"] == len(L.LISTS)
    assert _sitemap(env, "best") == {x["path"] for x in lists["lists"] if x["indexable"]}
    alt = env.get("/catalog/models/tesla/model-3/alternatives")
    assert alt.status_code == 200 and alt.json()["market"] in alt.json()["markets"]
    assert env.get("/catalog/models/tesla/model-3/alternatives?market=ZZ").status_code == 400
    assert env.get("/catalog/models/tesla/nope/alternatives").status_code == 404


def test_real_every_selected_pair_and_sitemap(real_db):
    env = real_db["env"]
    data = env.get("/catalog/compare-pairs").json()
    pairs = data["pairs"]
    assert data["indexed"] <= CP.MAX_INDEXED_PAIRS
    keys = [p["key"] for p in pairs]
    assert len(keys) == len(set(keys))
    for p in pairs:
        a, b = p["key"].split("-vs-") if p["key"].count("-vs-") == 1 else (None, None)
        assert a and a < b, p["key"]
        d = env.get("/catalog/compare/%s/%s" % (b, a)).json()          # reversed input
        assert d["path"] == p["path"] and d["indexable"] == p["indexable"], p["key"]
        for m in d["markets"]:
            dm = d if m == d["market"] else env.get("/catalog/compare/%s/%s?market=%s" % (a, b, m)).json()
            for r in dm["rows"]:
                st, x, y = r["compare"]["status"], r["a"], r["b"]
                if st in ("a_higher", "b_higher", "equal") and r["kind"] == "number":
                    assert (x["unit"], x["cycle"], x["market"], x["basis"]) == (y["unit"], y["cycle"], y["market"], y["basis"])
                if st == "not_comparable":
                    assert r["compare"]["delta"] is None and r["highlight"] is None
                if r["highlight"]:
                    assert st in ("a_higher", "b_higher")
                _check_text(r["text"], names_in(dm))
            for s in dm["summary"] + [f["q"] + " " + f["a"] for f in dm["faq"]]:
                _check_text(s, names_in(dm))
        if p["indexable"] and p["source"] != "pinned":
            assert d["quality"]["comparable_facts"] >= CP.MIN_COMPARABLE_FACTS
            assert d["quality"]["has_price"] and d["quality"]["has_range"]
    assert _sitemap(env, "compare") == {p["path"] for p in pairs if p["indexable"]}
    import routers.seo
    for pin in routers.seo.COMPARE_PAIRS:
        a, b = pin.split("-vs-")
        assert a < b, pin                                          # the pinned list is canonical
        r = env.get("/catalog/compare/%s/%s" % (a, b))
        if r.status_code == 200:
            assert r.json()["indexable"] is True, pin
    print("pairs:", len(pairs), "indexable:", data["indexed"], data["by_source"])


def test_real_alternatives_every_current_model(real_db):
    env = real_db["env"]
    for card in env.get("/catalog/models?status=current&commercial=false").json()["models"]:
        r = env.get("/catalog/models/%s/%s/alternatives" % (card["make"]["slug"], card["url_slug"]))
        assert r.status_code == 200, card["path"]
        d = r.json()
        assert len(d["alternatives"]) <= CP.ALTERNATIVES_MAX and len(d["compare"]) <= CP.ALT_COMPARE_MAX
        assert len(d["lists"]) <= CP.ALT_LISTS_MAX
        if d["rule"]:
            _check_text(d["rule"], names_in(d))
        for a in d["alternatives"]:
            assert a["card"]["slug"] != card["slug"] and a["card"]["body_style"] == card["body_style"]
