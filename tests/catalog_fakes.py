"""In-memory catalogs for the compare/list tests: a Catalog with the attributes a loaded one has
(statuses computed by Catalog._compute_status), built without a database."""
import random
import re
from collections import defaultdict

from services.catalog_service import Catalog

BANNED = re.compile(r"\b(better|worse|improved|improvement|upgrade|downgrade|dropped|new|winner|best)\b", re.I)


def off(market="US", my=2026, price=None, launch=None, currency=None, basis="msrp_excl_destination",
        rng=None, cycle=None, connector=None, est=False):
    currency = currency or {"US": "USD", "UK": "GBP", "EU": "EUR", "CN": "CNY"}.get(market)
    cycle = cycle or {"US": "EPA", "UK": "WLTP", "EU": "WLTP", "CN": "CLTC"}.get(market)
    return {"market": market, "model_year": my, "current_price": price, "launch_price": launch,
            "currency": currency if (price or launch) else None, "price_basis": basis if (price or launch) else None,
            "range_value": rng, "range_unit": ("mi" if cycle == "EPA" else "km") if rng else None,
            "range_cycle": cycle if rng else None, "connector": connector, "is_estimate": est}


def trim(name, offers=(), status=None, **specs):
    v = {"variant_name": name, "status": status, "offers": list(offers), "seats": None, "battery_kwh": None,
         "battery_basis": None, "power_hp": None, "accel_0_60_s": None, "accel_0_100_s": None,
         "top_speed_mph": None, "dc_kw": None, "drivetrain": None}
    v.update(specs)
    return v


def model(slug, make, body="suv", trims=(), status="current", markets=("US",), commercial=False, make_status="active"):
    return {"slug": slug, "make": make, "body": body, "trims": list(trims), "status": status,
            "markets": markets, "commercial": commercial, "make_status": make_status}


def build(specs, relations=(), shuffle=None):
    """A Catalog built in memory (no DB) with the same attributes and statuses as a loaded one."""
    if shuffle is not None:
        specs = list(specs)
        random.Random(shuffle).shuffle(specs)
    cat = Catalog.__new__(Catalog)
    cat.conn, cat.partial, cat.derived = None, False, {}
    cat.makes, cat.models, cat.gens, cat.variants = {}, {}, {}, {}
    cat.offerings, cat.images, cat.markets = defaultdict(list), defaultdict(list), defaultdict(dict)
    make_ids, ids = {}, {}
    vid = 1000
    for s in sorted(specs, key=lambda s: s["slug"]):   # ids by slug so a shuffle changes only dict order
        ids[s["slug"]] = len(ids) + 1
    for s in specs:
        if s["make"] not in make_ids:
            make_ids[s["make"]] = len(make_ids) + 1
        mk_id = make_ids[s["make"]]
        cat.makes[mk_id] = {"id": mk_id, "slug": s["make"], "catalog_name": s["make"].title(),
                            "catalog_status": s["make_status"], "status_date": None}
        mid = ids[s["slug"]]
        cat.models[mid] = {"id": mid, "make_id": mk_id, "slug": s["slug"], "url_slug": s["slug"].split("-", 1)[1],
                           "name": s["slug"].split("-", 1)[1].title(), "body_style": s["body"], "status": s["status"],
                           "is_commercial": s["commercial"], "aliases": [], "official_url": None, "updated_at": None,
                           "sources": [], "description": None}
        gid = mid * 10
        cat.gens[gid] = {"id": gid, "model_id": mid, "slug": "2024", "name": "First generation", "kind": "generation",
                         "ordinal": 1, "start_year": 2024, "end_year": None, "status": None, "description": None,
                         "updated_at": None, "sources": [], "code_name": None, "platform": None}
        for i, t in enumerate(s["trims"]):
            vid += 1
            v = {k: val for k, val in t.items() if k != "offers"}
            v.update(id=vid, generation_id=gid, variant_slug=re.sub(r"[^a-z0-9]+", "-", t["variant_name"].lower()),
                     variant_order=i, sources=[], catalog_updated_at=None, year_from=None, year_to=None,
                     body_type=None, torque_lbft=None)
            cat.variants[vid] = v
            cat.offerings[vid] = [dict(o) for o in t["offers"]]
        for code in s["markets"]:
            cat.markets[mid][code] = {"model_id": mid, "market": code, "status": "current" if s["status"] == "current"
                                      else s["status"], "local_name": None, "launch_date": None, "end_date": None}
    cat.gens_by_model, cat.variants_by_gen = defaultdict(list), defaultdict(list)
    for g in cat.gens.values():
        cat.gens_by_model[g["model_id"]].append(g)
    for v in cat.variants.values():
        cat.variants_by_gen[v["generation_id"]].append(v)
    cat._compute_status()
    cat.relation_rows = [{"model_id": ids[a], "related_model_id": ids[b], "relation": r} for a, b, r in relations]
    return cat


def us_suv(slug, make, price, rng, dc=None, accel=None, basis="msrp_excl_destination", body="suv", **kw):
    return model(slug, make, body, [trim("Base", [off(price=price, rng=rng, basis=basis, connector="NACS")],
                                         dc_kw=dc, accel_0_60_s=accel, seats=5)], **kw)


# ---------------------------------------------------------------- API helpers

def _sitemap(env, prefix):
    body = env.get("/catalog/sitemap.xml").text
    return set(re.findall(r"<loc>https://www\.evlineup\.org(/%s/[^<]+)</loc>" % prefix, body))


def _check_text(s, names=()):
    """Structure on the raw text; banned words after removing names that come from the data."""
    assert s and "None" not in s and "()" not in s and "  " not in s and " ." not in s and ",," not in s, s
    t = s
    for nm in sorted({n for n in names if n}, key=len, reverse=True):
        t = t.replace(nm, "").replace(nm.replace("(", "[").replace(")", "]"), "")
    assert not BANNED.search(t), s


def names_in(d) -> list:
    """Model and trim names a compare/alternatives/list response carries (data, may contain any word)."""
    out = []
    for side in ("a", "b"):
        if isinstance(d.get(side), dict):
            out.append(d[side].get("name"))
    if isinstance(d.get("model"), dict):
        out.append(d["model"].get("name"))
    for r in d.get("rows", []):
        for side in ("a", "b"):
            if r.get(side) and r[side].get("variant"):
                out.append(r[side]["variant"].get("name"))
    for a in d.get("alternatives", []):
        out += [a["card"]["name"], a["card"]["make"]["name"]]
    return out
