"""Version-change pages (services/catalog_changes.py): pure rules, the fixture DB and a real-data smoke."""
import re

import services.catalog_changes as C
import validate_seed

BANNED = re.compile(r"\b(better|worse|improved|improvement|upgrade|downgrade|dropped|new)\b", re.I)


# ---------------------------------------------------------------- builders

def gen(id, slug, start, status="current", kind="generation", ordinal=1, end=None, name=None):
    return {"id": id, "slug": slug, "name": name or slug, "kind": kind, "ordinal": ordinal,
            "start_year": start, "end_year": end, "_status": status}


def var(id, slug, name, drivetrain=None, status="current", order=None, **specs):
    v = {"id": id, "variant_slug": slug, "variant_name": name, "drivetrain": drivetrain, "_status": status,
         "variant_order": order, "seats": None, "battery_kwh": None, "battery_basis": None, "power_hp": None,
         "accel_0_60_s": None, "accel_0_100_s": None, "top_speed_mph": None, "dc_kw": None}
    v.update(specs)
    return v


def off(market="US", my=2024, price=None, launch=None, currency="USD", basis="msrp_excl_destination",
        rng=None, unit="mi", cycle="EPA", connector="NACS", est=False):
    return {"market": market, "model_year": my, "current_price": price, "launch_price": launch,
            "currency": currency if (price or launch) else None, "price_basis": basis if (price or launch) else None,
            "range_value": rng, "range_unit": unit if rng else None, "range_cycle": cycle if rng else None,
            "connector": connector, "is_estimate": est}


def rows_for(go, vo, gn, vn, offers, market="US"):
    return {r["key"]: r for r in C.diff(C.side(go, vo, offers, market), C.side(gn, vn, offers, market), market)}


# ---------------------------------------------------------------- pairs

def test_adjacent_pairs_skip_cancelled_and_order_oldest_first():
    gens = [gen(3, "2024", 2024), gen(1, "2017", 2017, "discontinued"), gen(2, "2021", 2021, "cancelled"),
            gen(4, "2024-refresh", 2024, kind="refresh", ordinal=2)]
    pairs = [(a["slug"], b["slug"]) for a, b in C.adjacent_pairs(gens)]
    assert pairs == [("2017", "2024"), ("2024", "2024-refresh")]
    assert [g["slug"] for g in C.find_pair(gens, "2024", "2017")] == ["2017", "2024"]   # reversed input
    assert C.find_pair(gens, "2017", "2024-refresh") is None                           # not adjacent
    assert C.find_pair(gens, "2017", "2021") is None                                   # cancelled
    assert C.find_pair(gens, "2017", "2017") is None
    assert C.find_pair(gens, "2017", "nope") is None


# ---------------------------------------------------------------- trims

def test_match_trims_model3_aliases():
    older = [var(1, "long-range-rwd", "Long Range RWD", "RWD"), var(2, "long-range-awd", "Long Range AWD", "AWD"),
             var(3, "performance", "Performance AWD", "AWD"), var(4, "standard-range", "Standard Range RWD", "RWD")]
    newer = [var(11, "premium-rwd", "Premium RWD (Long Range RWD)", "RWD"),
             var(12, "premium-awd", "Premium AWD (Long Range AWD)", "AWD"),
             var(13, "performance", "Performance", "AWD"), var(14, "standard-rwd", "Standard RWD", "RWD")]
    matched, only_o, only_n = C.match_trims(older, newer)
    got = {(a["variant_slug"], b["variant_slug"], how) for a, b, how in matched}
    assert got == {("performance", "performance", "slug"), ("long-range-rwd", "premium-rwd", "alias"),
                   ("long-range-awd", "premium-awd", "alias")}
    assert [v["variant_slug"] for v in only_o] == ["standard-range"]
    assert [v["variant_slug"] for v in only_n] == ["standard-rwd"]   # never matched on drivetrain alone


def test_match_trims_rejects_drivetrain_conflict_and_ambiguity():
    matched, _, _ = C.match_trims([var(1, "gt", "GT", "AWD")], [var(2, "gt", "GT", "RWD")])
    assert matched == []
    # name match, case/punctuation-insensitive
    matched, _, _ = C.match_trims([var(1, "a", "Long-Range AWD", "AWD")], [var(2, "b", "long range awd", None)])
    assert [(how) for _, _, how in matched] == ["name"]
    # two candidates for one alias: no match (strict, at most one per variant)
    matched, _, _ = C.match_trims([var(1, "x", "Long Range")],
                                  [var(2, "y", "Premium (Long Range)"), var(3, "z", "Sport (Long Range)")])
    assert matched == []


# ---------------------------------------------------------------- rows

def test_price_groups_never_cross_basis_and_use_newest_year_in_shared_group():
    go, gn = gen(1, "2017", 2017, "discontinued"), gen(2, "2024", 2024)
    vo, vn = [var(1, "a", "A")], [var(2, "b", "B")]
    offers = {1: [off(my=2019, launch=35000)],
              2: [off(my=2026, price=36990), off(my=2027, price=38380, basis="msrp_incl_destination")]}
    r = rows_for(go, vo, gn, vn, offers)["entry_price"]
    assert r["change"]["status"] == "increased" and r["change"]["delta"] == 1990
    assert r["older"]["price_kind"] == "launch" and r["older"]["model_year"] == 2019
    assert r["newer"]["model_year"] == 2026 and r["newer"]["basis"] == "msrp_excl_destination"
    # only different bases -> not comparable, no delta
    offers = {1: [off(my=2025, price=40000, basis="msrp_incl_destination")], 2: [off(my=2026, price=39000)]}
    r = rows_for(go, vo, gn, vn, offers)["entry_price"]
    assert r["change"]["status"] == "not_comparable" and r["change"]["delta"] is None
    assert "different bases" in r["change"]["reason"]
    assert r["older"]["value"] == 40000 and r["newer"]["value"] == 39000


def test_range_cycles_battery_basis_and_missing_sides():
    go, gn = gen(1, "2021", 2021, "discontinued"), gen(2, "2024", 2024)
    vo = [var(1, "a", "A", battery_kwh=77.4, battery_basis="gross", power_hp=300)]
    vn = [var(2, "a", "A", battery_kwh=84.0, battery_basis="usable", power_hp=None, dc_kw=250)]
    offers = {1: [off("EU", None, rng=500, unit="km", cycle="WLTP")], 2: [off("EU", None, rng=520, unit="km", cycle="NEDC")]}
    rows = rows_for(go, vo, gn, vn, offers, "EU")
    assert rows["longest_range"]["change"]["status"] == "not_comparable"
    assert rows["largest_battery"]["change"]["status"] == "not_comparable"
    assert rows["most_power"]["change"]["status"] == "missing_newer"
    assert rows["fastest_dc"]["change"]["status"] == "missing_older"
    assert "Not on file for the 2021" in C.row_text(rows["fastest_dc"], ("2021", "2024"), "EU")
    for r in rows.values():
        if r["change"]["status"] in C.COMPARED:
            assert r["older"] and r["newer"] and r["older"]["value"] is not None and r["newer"]["value"] is not None
    # both bases unknown: values compared, flagged, not counted
    vo[0]["battery_basis"] = vn[0]["battery_basis"] = None
    r = rows_for(go, vo, gn, vn, offers, "EU")["largest_battery"]
    assert r["change"]["basis_unknown"] and not C.is_comparable(r)
    assert C.BATTERY_UNKNOWN in C.row_text(r, ("2021", "2024"), "EU")


def test_pick_market_prefers_us_then_most_comparable():
    go, gn = gen(1, "2021", 2021), gen(2, "2024", 2024)
    vo, vn = [var(1, "a", "A")], [var(2, "a", "A")]
    both_us = {1: [off("US", 2023, rng=300), off("EU", None, rng=500, unit="km", cycle="WLTP")],
               2: [off("US", 2025, rng=310), off("EU", None, rng=520, unit="km", cycle="WLTP")]}
    assert C.pick_market(go, vo, gn, vn, both_us) == "US"
    no_us = {1: [off("CN", None, rng=500, unit="km", cycle="CLTC"), off("EU", None, price=40000, currency="EUR", basis="list_incl_vat")],
             2: [off("CN", None, rng=520, unit="km", cycle="CLTC"), off("EU", None, rng=400, unit="km", cycle="WLTP")]}
    assert C.pick_market(go, vo, gn, vn, no_us) == "CN"
    assert C.pick_market(go, vo, gn, vn, {}) is None


def test_summary_and_faq_are_neutral_and_data_backed():
    go = gen(1, "2017", 2017, "discontinued", end=2023, name="Original")
    gn = gen(2, "2024", 2024, kind="refresh", name="Highland")
    vo = [var(1, "p", "Performance", "AWD", accel_0_60_s=3.1, top_speed_mph=162, dc_kw=250)]
    vn = [var(2, "p", "Performance", "AWD", accel_0_60_s=2.9, top_speed_mph=163, dc_kw=250)]
    offers = {1: [off(my=2023, rng=315)], 2: [off(my=2026, rng=309)]}
    so, sn = C.side(go, vo, offers, "US"), C.side(gn, vn, offers, "US")
    rows = C.diff(so, sn, "US")
    assert C.comparable_facts(rows) == 4
    labels = C.gen_labels(go, gn)
    s = C.summary("Tesla Model 3", go, gn, "refresh", rows, "US", labels)
    assert s[0] == "Tesla Model 3 Highland (2024–present) is a refresh of the Original (2017–2023)."
    assert any("No US price is on file for either version." == x for x in s)
    faq = C.faq("Tesla Model 3", rows, "US", labels, (C.model_years(so), C.model_years(sn)))
    qs = [f["q"] for f in faq]
    assert not any("expensive" in q for q in qs)           # price not comparable: no price question
    assert any("more range" in q for q in qs) and any("charge faster" in q for q in qs)
    text = " ".join(s + [f["a"] for f in faq] + [C.row_text(r, labels, "US") for r in rows])
    assert not BANNED.search(text), BANNED.search(text)
    # upcoming newer generation: tense + estimate tags
    gn["_status"] = "upcoming"
    rows = C.diff(C.side(go, vo, offers, "US"), C.side(gn, vn, offers, "US"), "US")
    s = C.summary("Tesla Model 3", go, gn, "refresh", rows, "US", labels)
    assert "upcoming refresh" in s[0] and "not on sale yet" in s[1]
    assert all(r["newer"]["is_estimate"] for r in rows if r.get("newer"))


def test_validator_rejects_changes_like_generation_slugs():
    def doc(slug):
        return {"make": {"slug": "x", "name": "X", "status": "active", "sources": []},
                "models": [{"slug": "x-a", "url_slug": "a", "name": "A", "body_style": "suv", "status": "current",
                            "generations": [{"slug": slug, "name": "G", "kind": "generation", "start_year": 2024,
                                             "status": "current", "variants": []}]}]}
    for slug, bad in (("2024", False), ("2024-vs-2025", True), ("changes", True)):
        rep = validate_seed.Report()
        validate_seed.FileCheck(rep, "x.json").run(doc(slug))
        hit = [e for e in rep.errors if "must not be 'changes'" in e["message"]]
        assert bool(hit) == bad, (slug, rep.errors)


# ---------------------------------------------------------------- API (fixture DB, real DB)

def _sitemap_changes(env):
    body = env.get("/catalog/sitemap.xml").text
    return set(re.findall(r"<loc>https://www\.evlineup\.org(/make/[^<]+/changes/[^<]+)</loc>", body))


def _check_page(env, path):
    r = env.get("/catalog/changes/" + path[len("/make/"):].replace("/changes/", "/").replace("-vs-", "/"))
    assert r.status_code == 200, path
    d = r.json()
    assert d["path"] == path
    names = [d["model"]["name"], d["make"]["name"], d["older"]["name"], d["newer"]["name"]] + \
        [t[s]["name"] for t in d["trims"]["matched"] for s in ("older", "newer")] + \
        [v["name"] for v in d["trims"]["only_older"] + d["trims"]["only_newer"]] + \
        [row[s]["variant"]["name"] for row in d["rows"] for s in ("older", "newer")
         if row.get(s) and row[s].get("variant")]

    def clean(t):   # names come from the data and may contain any word
        for nm in sorted({n for n in names if n}, key=len, reverse=True):
            t = t.replace(nm, "").replace(nm.replace("(", "[").replace(")", "]"), "")
        return t
    for row in d["rows"] + [x for t in d["trims"]["matched"] for x in t["rows"]]:
        st, o, n = row["change"]["status"], row["older"], row["newer"]
        if st in ("increased", "decreased", "unchanged"):
            assert o and n and o["value"] is not None and n["value"] is not None, (path, row)
            if row["kind"] == "number":   # same comparability group on both sides
                assert (o["unit"], o["cycle"], o["market"], o["basis"]) == (n["unit"], n["cycle"], n["market"], n["basis"]), row
        if st == "not_comparable":
            assert row["change"]["delta"] is None and row["change"]["reason"]
        assert not BANNED.search(clean(row["text"])), row["text"]
    for s in d["summary"] + [f["q"] + " " + f["a"] for f in d["faq"]]:
        assert not BANNED.search(clean(s)), s
    if not d["indexable"]:
        assert d["quality"]["default_market_comparable_facts"] < C.MIN_COMPARABLE_FACTS
    return d


def test_fixture_changes_endpoint(fixture_db):
    env = fixture_db["env"]
    tree = env.get("/catalog/models/tesla/model-3").json()
    assert [c["path"] for c in tree["changes"]] == ["/make/tesla/model-3/changes/2017-vs-2024"]
    d = _check_page(env, "/make/tesla/model-3/changes/2017-vs-2024")
    rev = env.get("/catalog/changes/tesla/model-3/2024/2017")
    assert rev.status_code == 200 and rev.json()["path"] == d["path"]
    assert d["relation"] == "refresh" and d["older"]["slug"] == "2017" and d["newer"]["slug"] == "2024"
    assert env.get("/catalog/changes/tesla/model-3/2017/2017").status_code == 404
    assert env.get("/catalog/changes/tesla/model-3/2017/1999").status_code == 404
    assert env.get("/catalog/changes/tesla/nope/2017/2024").status_code == 404
    assert env.get("/catalog/changes/tesla/model-3/2017/2024?market=JP").status_code == 400
    sm = _sitemap_changes(env)
    assert (d["path"] in sm) == d["indexable"]


def test_real_changes_every_pair_and_sitemap(real_db):
    env = real_db["env"]
    sm = _sitemap_changes(env)
    indexable, total = set(), 0
    for card in env.get("/catalog/models").json()["models"]:
        tree = env.get("/catalog/models/%s/%s" % (card["make"]["slug"], card["url_slug"])).json()
        for ch in tree["changes"]:
            total += 1
            d = _check_page(env, ch["path"])
            assert d["indexable"] == ch["indexable"]
            if ch["indexable"]:
                indexable.add(ch["path"])
        gens = [g for g in tree["generations"] if g["status"] != "cancelled"]
        if len(gens) >= 3:   # newest vs oldest is never a page
            k = tree["model"]["key"]
            assert env.get("/catalog/changes/%s/%s/%s" % (k, gens[-1]["slug"], gens[0]["slug"])).status_code == 404
    print("pairs:", total, "indexable:", len(indexable))
    assert sm == indexable


def test_real_model3_alias_matching(real_db):
    r = real_db["env"].get("/catalog/changes/tesla/model-3/2024/2017")
    if r.status_code == 404:   # tesla.json not loaded in this checkout
        return
    d = r.json()
    assert d["path"] == "/make/tesla/model-3/changes/2017-vs-2024"
    pairs = {(m["older"]["slug"], m["newer"]["slug"]): m["match"] for m in d["trims"]["matched"]}
    assert pairs.get(("long-range-awd", "premium-awd")) == "alias"
    assert pairs.get(("long-range-rwd", "premium-rwd")) == "alias"
    price = next(x for x in d["rows"] if x["key"] == "entry_price")
    assert price["older"]["basis"] == price["newer"]["basis"] == "msrp_excl_destination"
