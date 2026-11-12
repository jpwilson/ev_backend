"""Generated "best" lists (/best/{key}): one declarative registry, one market per list.

Pure functions over a whole-catalog snapshot (services/catalog_service.cached_catalog). Rules
(FEATURES_BRIEF_2.md, "Lists"):
  - A model qualifies only if it is on sale (current) in the list's market, not commercial, and its
    brand is not defunct. Figures come from the trims of its default (current) version sold there.
  - Price: lowest current published price in the market's currency (launch-only and estimated prices
    left out); every item names its price basis. Range: the market's main test cycle only. 0-60 mph in
    the US, 0-100 km/h elsewhere, never mixed. Charging: highest published DC peak.
  - Cars missing the ranking figure are counted (`excluded`), never ranked last.
  - Gates decide `indexable`: at least MIN_ITEMS ranked; a price-ceiling list must differ from the next
    lower ceiling by CEILING_MIN_DIFF models; a list whose top 10 overlaps an indexable higher-priority
    list in the same market by OVERLAP_MAX or more is not indexable.
No values are converted; no list mixes currencies or test cycles.
"""
from typing import Dict, List, Optional

import services.catalog_status as S
from services.catalog_changes import MARKET_IN, PRICE_BASIS_TEXT, _fmt_num, _money, _newest_first, display_name
from services.catalog_service import MARKETS, PRIMARY_RANGE_CYCLE, _num, _variant_order

MAX_LISTS = 30
MAX_LIMIT = 25
MIN_ITEMS = 6
CEILING_MIN_DIFF = 3
OVERLAP_TOP = 10
OVERLAP_MAX = 0.7
# The seven lists that existed before the registry. Their URLs are already indexed and
# linked, so the quality gates never switch them to noindex.
ESTABLISHED = frozenset({"cheapest-evs", "longest-range-evs", "fastest-evs", "evs-under-40k",
                         "3-row-evs", "electric-trucks", "300-mile-range-evs"})
RELATED_MAX = 4

MARKET_CURRENCY = {"US": "USD", "CA": "CAD", "EU": "EUR", "UK": "GBP", "CN": "CNY", "JP": "JPY",
                   "KR": "KRW", "IN": "INR", "AU": "AUD"}
MARKET_TITLE = {"US": "the US", "EU": "Europe", "UK": "the UK", "CN": "China"}
BODY_PLURAL = {"suv": "SUVs", "sedan": "sedans", "hatchback": "hatchbacks", "wagon": "wagons", "coupe": "coupes",
               "convertible": "convertibles", "pickup": "pickup trucks", "van": "vans", "minivan": "minivans",
               "microcar": "microcars"}
BODY_SINGULAR = {"suv": "SUV", "pickup": "pickup truck"}
OLD_METRIC = {"price_asc": "price", "range_desc": "range", "accel_asc": "accel", "dc_desc": "dc",
              "markets_desc": "markets"}

# Registry: priority order (earlier lists win the overlap gate). The 7 original US keys keep their
# URLs; `evs-under-40k` now ranks by range and `300-mile-range-evs` by price, so neither repeats
# `cheapest-evs` / `longest-range-evs`.
LISTS = [
    # --- US (no suffix)
    {"key": "cheapest-evs", "market": "US", "metric": "price_asc", "limit": 12,
     "title": "Cheapest Electric Cars", "h1": "Cheapest electric cars in the US",
     "blurb": "Every electric car on sale in the US, ranked by its lowest published price, cheapest first."},
    {"key": "longest-range-evs", "market": "US", "metric": "range_desc", "limit": 12,
     "title": "Longest Range Electric Cars", "h1": "Longest range electric cars in the US",
     "blurb": "Every electric car on sale in the US, ranked by EPA range, longest first."},
    {"key": "fastest-evs", "market": "US", "metric": "accel_asc", "limit": 12,
     "title": "Fastest Electric Cars (0-60 mph)", "h1": "Fastest electric cars in the US, 0–60 mph",
     "blurb": "Every electric car on sale in the US, ranked by its quickest published 0–60 mph time."},
    {"key": "evs-under-40k", "market": "US", "metric": "range_desc", "limit": 12, "filters": {"max_price": 40000},
     "title": "EVs Under $40,000, Ranked by Range", "h1": "Electric cars under $40,000, longest range first",
     "blurb": "Every electric car on sale in the US with a published price under $40,000, ranked by EPA range, "
              "longest first."},
    {"key": "3-row-evs", "market": "US", "metric": "range_desc", "limit": 12, "filters": {"min_seats": 6},
     "title": "Best 3-Row Electric SUVs (6+ Seats)", "h1": "Electric cars with six or more seats",
     "blurb": "Every electric car on sale in the US with a trim seating six or more, ranked by EPA range, "
              "longest first."},
    {"key": "electric-trucks", "market": "US", "metric": "range_desc", "limit": 12,
     "filters": {"body_style": "pickup"}, "include_upcoming": True,
     "title": "Electric Pickup Trucks", "h1": "Electric pickup trucks",
     "blurb": "Every electric pickup truck on sale in the US, ranked by EPA range, then the ones coming soon."},
    {"key": "300-mile-range-evs", "market": "US", "metric": "price_asc", "limit": 15, "filters": {"min_range": 300},
     "title": "EVs with 300+ Miles of Range, Cheapest First",
     "h1": "Electric cars with 300+ miles of EPA range, cheapest first",
     "blurb": "Every electric car on sale in the US with an EPA range of 300 miles or more, ranked by "
              "lowest published price."},
    {"key": "evs-under-30k", "market": "US", "metric": "range_desc", "limit": 15, "filters": {"max_price": 30000},
     "title": "EVs Under $30,000, Ranked by Range", "h1": "Electric cars under $30,000, longest range first",
     "blurb": "Every electric car on sale in the US with a published price under $30,000, ranked by EPA range, "
              "longest first."},
    {"key": "evs-under-50k", "market": "US", "metric": "range_desc", "limit": 15, "filters": {"max_price": 50000},
     "title": "EVs Under $50,000, Ranked by Range", "h1": "Electric cars under $50,000, longest range first",
     "blurb": "Every electric car on sale in the US with a published price under $50,000, ranked by EPA range, "
              "longest first."},
    {"key": "cheapest-electric-suvs", "market": "US", "metric": "price_asc", "limit": 15,
     "filters": {"body_style": "suv"},
     "title": "Cheapest Electric SUVs", "h1": "Cheapest electric SUVs in the US",
     "blurb": "Every electric SUV on sale in the US, ranked by its lowest published price, cheapest first."},
    {"key": "electric-sedans", "market": "US", "metric": "range_desc", "limit": 15, "filters": {"body_style": "sedan"},
     "title": "Electric Sedans, Ranked by Range", "h1": "Electric sedans in the US, longest range first",
     "blurb": "Every electric sedan on sale in the US, ranked by EPA range, longest first."},
    {"key": "fastest-charging-evs", "market": "US", "metric": "dc_desc", "limit": 15,
     "title": "Fastest-Charging EVs (Peak DC Power)", "h1": "Electric cars with the highest DC charging peak in the US",
     "blurb": "Every electric car on sale in the US, ranked by the highest DC fast-charging power its maker "
              "publishes. A peak figure, not a charging time."},
    {"key": "evs-with-nacs", "market": "US", "metric": "price_asc", "limit": 15, "filters": {"connector": "NACS"},
     "title": "EVs with a NACS Port, Cheapest First",
     "h1": "Electric cars with a built-in NACS (Tesla-style) charging port, cheapest first",
     "blurb": "Every electric car on sale in the US with a NACS charging port on file, ranked by lowest "
              "published price."},
    # --- UK
    {"key": "cheapest-evs-uk", "market": "UK", "metric": "price_asc", "limit": 15,
     "title": "Cheapest Electric Cars in the UK", "h1": "Cheapest electric cars in the UK",
     "blurb": "Every electric car on sale in the UK, ranked by its lowest published list price, cheapest first."},
    {"key": "evs-under-30k-uk", "market": "UK", "metric": "range_desc", "limit": 15, "filters": {"max_price": 30000},
     "title": "EVs Under £30,000 in the UK, Ranked by Range", "h1": "Electric cars under £30,000 in the UK, longest range first",
     "blurb": "Every electric car on sale in the UK with a published list price under £30,000, ranked by WLTP "
              "range, longest first."},
    {"key": "longest-range-evs-uk", "market": "UK", "metric": "range_desc", "limit": 15,
     "title": "Longest Range Electric Cars in the UK", "h1": "Longest range electric cars in the UK",
     "blurb": "Every electric car on sale in the UK, ranked by WLTP range, longest first."},
    {"key": "7-seat-evs-uk", "market": "UK", "metric": "range_desc", "limit": 15, "filters": {"min_seats": 7},
     "title": "7-Seat Electric Cars in the UK", "h1": "Electric cars with seven or more seats in the UK",
     "blurb": "Every electric car on sale in the UK with a trim seating seven or more, ranked by WLTP range, "
              "longest first."},
    {"key": "cheapest-electric-suvs-uk", "market": "UK", "metric": "price_asc", "limit": 15,
     "filters": {"body_style": "suv"},
     "title": "Cheapest Electric SUVs in the UK", "h1": "Cheapest electric SUVs in the UK",
     "blurb": "Every electric SUV on sale in the UK, ranked by its lowest published list price, cheapest first."},
    {"key": "fastest-charging-evs-uk", "market": "UK", "metric": "dc_desc", "limit": 15,
     "title": "Fastest-Charging EVs in the UK", "h1": "Electric cars with the highest DC charging peak in the UK",
     "blurb": "Every electric car on sale in the UK, ranked by the highest DC fast-charging power its maker "
              "publishes. A peak figure, not a charging time."},
    # --- Europe (EU market = EEA + Switzerland). No price rankings: the country behind an EU price is not recorded.
    {"key": "longest-range-evs-europe", "market": "EU", "metric": "range_desc", "limit": 15,
     "title": "Longest Range Electric Cars in Europe", "h1": "Longest range electric cars in Europe",
     "blurb": "Every electric car on sale in Europe, ranked by WLTP range, longest first."},
    {"key": "7-seat-evs-europe", "market": "EU", "metric": "range_desc", "limit": 15, "filters": {"min_seats": 7},
     "title": "7-Seat Electric Cars in Europe", "h1": "Electric cars with seven or more seats in Europe",
     "blurb": "Every electric car on sale in Europe with a trim seating seven or more, ranked by WLTP range, "
              "longest first."},
    {"key": "fastest-charging-evs-europe", "market": "EU", "metric": "dc_desc", "limit": 15,
     "title": "Fastest-Charging EVs in Europe", "h1": "Electric cars with the highest DC charging peak in Europe",
     "blurb": "Every electric car on sale in Europe, ranked by the highest DC fast-charging power its maker "
              "publishes. A peak figure, not a charging time."},
    {"key": "small-evs-europe", "market": "EU", "metric": "range_desc", "limit": 15,
     "filters": {"body_style": ("hatchback", "microcar")},
     "title": "Small Electric Cars in Europe, Ranked by Range",
     "h1": "Small electric cars (hatchbacks and microcars) in Europe, longest range first",
     "blurb": "Every electric hatchback and microcar on sale in Europe, ranked by WLTP range, longest first."},
    # --- China
    {"key": "cheapest-evs-china", "market": "CN", "metric": "price_asc", "limit": 15,
     "title": "Cheapest Electric Cars in China", "h1": "Cheapest electric cars in China",
     "blurb": "Every electric car on sale in China, ranked by its lowest published price in yuan, cheapest first."},
    {"key": "longest-range-evs-china", "market": "CN", "metric": "range_desc", "limit": 15,
     "title": "Longest Range Electric Cars in China", "h1": "Longest range electric cars in China (CLTC)",
     "blurb": "Every electric car on sale in China, ranked by CLTC range, longest first. CLTC figures are "
              "higher than EPA or WLTP figures for the same car and are not comparable with them."},
    # --- anywhere but the US
    {"key": "evs-not-sold-in-us", "market": None, "metric": "markets_desc", "limit": 25,
     "filters": {"not_sold_in": "US"},
     "title": "Electric Cars Not Sold in the US", "h1": "Electric cars on sale elsewhere but not in the US",
     "blurb": "Electric cars on sale in at least one market in our data with no current US listing in our "
              "data, ranked by how many markets they are on sale in."},
]
LIST = {c["key"]: c for c in LISTS}
assert len(LISTS) <= MAX_LISTS and len(LIST) == len(LISTS)

PRICE_EXCL_NOTE = 'Prices marked "excluding destination" cost more than shown: the destination charge is extra.'
RANGE_NOTE = "Ranges are rated %s figures as published; real-world range is usually lower in cold weather and at highway speed."
DC_NOTE = "DC charging figures are the peak power as published, not a charging time."
UPCOMING_NOTE = "Cars not on sale yet are listed after the ones on sale; their figures are manufacturer estimates."


# ---------------------------------------------------------------- eligibility and per-market figures

def base_eligible(cat, m) -> bool:
    """Not commercial, brand not defunct, and a default version that is not cancelled."""
    make = cat.makes[m["make_id"]]
    gen = cat.gens.get(m["_default_gen_id"])
    return (not m["is_commercial"] and not S.is_brand_defunct(make["catalog_status"])
            and gen is not None and gen["_status"] != "cancelled")


def market_status(cat, m, market) -> Optional[str]:
    mk = cat.markets[m["id"]].get(market)
    return mk["_status"] if mk else None


def on_sale(cat, m, market) -> bool:
    return m["_status"] == "current" and market_status(cat, m, market) == "current"


def current_markets(cat, m) -> List[str]:
    return [k for k in MARKETS if market_status(cat, m, k) == "current"] if m["_status"] == "current" else []


def accel_field(market) -> str:
    return "accel_0_60_s" if market in ("US", "CA") else "accel_0_100_s"


def accel_label(market) -> str:
    return "0–60 mph" if market in ("US", "CA") else "0–100 km/h"


def default_variants(cat, m) -> List[dict]:
    """Trims of the default version that are on sale (else upcoming, else any not cancelled), seed order:
    a discontinued trim of a current car is not what a buyer can get."""
    vs = sorted([v for v in cat.variants_by_gen.get(m["_default_gen_id"], []) if v["_status"] != "cancelled"],
                key=_variant_order)
    return ([v for v in vs if v["_status"] == "current"] or [v for v in vs if v["_status"] == "upcoming"] or vs)


def _clean(x):
    """Decimal/float -> int when whole (400.0 -> 400), else float."""
    x = _num(x)
    return int(x) if isinstance(x, float) and x.is_integer() else x


def market_facts(cat, m, market, allow_estimates=False) -> dict:
    """Figures of the model's default version in one market, each naming the trim it came from:
    price (lowest current price in the market currency, newest model year per trim), range (longest on
    the market's main cycle), accel (0-60 in the US/CA, else 0-100), dc (highest peak), seats (most),
    connectors. Trims counted are those with an offering in the market. Memoised on the cached catalog."""
    memo = getattr(cat, "derived", None)
    mkey = ("facts", m["id"], market, bool(allow_estimates))
    if memo is not None and mkey in memo:
        return memo[mkey]
    out = _market_facts(cat, m, market, allow_estimates)
    if memo is not None:
        memo[mkey] = out
    return out


def _market_facts(cat, m, market, allow_estimates):
    cur, cycle = MARKET_CURRENCY.get(market), PRIMARY_RANGE_CYCLE.get(market)
    scope, price, rng = [], None, None
    connectors = set()
    for v in default_variants(cat, m):
        offers = [o for o in cat.offerings.get(v["id"], []) if o["market"] == market]
        if not offers:
            continue
        scope.append(v)
        offers = _newest_first(offers)
        connectors.update(o["connector"] for o in offers if o["connector"])
        p = next((o for o in offers if o["current_price"] is not None and o["currency"] == cur
                  and (allow_estimates or not o["is_estimate"])), None)
        if p and (price is None or _clean(p["current_price"]) < price["value"]):
            price = {"value": _clean(p["current_price"]), "currency": p["currency"], "basis": p["price_basis"],
                     "market": market, "model_year": p["model_year"], "is_estimate": bool(p["is_estimate"]),
                     "variant": cat.variant_mini(v)}
        r = next((o for o in offers if o["range_value"] is not None and o["range_cycle"] == cycle
                  and (allow_estimates or not o["is_estimate"])), None)
        if r and (rng is None or _clean(r["range_value"]) > rng["value"]):
            rng = {"value": _clean(r["range_value"]), "unit": r["range_unit"], "cycle": r["range_cycle"],
                   "market": market, "model_year": r["model_year"], "is_estimate": bool(r["is_estimate"]),
                   "variant": cat.variant_mini(v)}
    out = {"market": market, "scope": scope, "price": price, "range": rng, "connectors": sorted(connectors),
           "accel": None, "dc": None, "seats": None}
    af = accel_field(market)
    for key, field, better in (("accel", af, min), ("dc", "dc_kw", max), ("seats", "seats", max)):
        cands = [v for v in scope if v.get(field) is not None]
        if cands:
            v = better(cands, key=lambda x: _num(x[field]))   # first in seed order on ties
            out[key] = {"value": _clean(v[field]), "unit": {"accel": "s", "dc": "kW", "seats": "seats"}[key],
                        "variant": cat.variant_mini(v)}
            if key == "accel":
                out[key]["label"] = accel_label(market)
    return out


# ---------------------------------------------------------------- text

def price_text(p) -> str:
    return _money(p["value"], p["currency"])


def basis_text(fact) -> Optional[str]:
    """'MSRP excluding destination, 2026 model year'."""
    bits = []
    if fact.get("basis"):
        bits.append(PRICE_BASIS_TEXT.get(fact["basis"], fact["basis"]))
    if fact.get("cycle"):
        bits.append(fact["cycle"])
    if fact.get("model_year"):
        bits.append("%d model year" % fact["model_year"])
    if fact.get("is_estimate"):
        bits.append("manufacturer estimate")
    return ", ".join(bits) or None


def fact_display(metric, fact) -> str:
    if metric == "price_asc":
        return price_text(fact)
    if metric == "range_desc":
        return "%s %s" % (_fmt_num(fact["value"]), fact["unit"])
    if metric == "accel_asc":
        return "%s s" % _fmt_num(fact["value"])
    if metric == "dc_desc":
        return "%s kW" % _fmt_num(fact["value"])
    if metric == "markets_desc":
        return "%d market%s" % (fact["value"], "" if fact["value"] == 1 else "s")
    return str(fact["value"])


def _where(market) -> str:
    if market == "EU":
        return "in Europe (EU market: EEA countries and Switzerland)"
    return "in %s" % MARKET_IN.get(market, market) if market else "outside the US"


def _noun(cfg) -> str:
    body = (cfg.get("filters") or {}).get("body_style")
    if not body:
        return "Cars"
    bodies = body if isinstance(body, tuple) else (body,)
    words = [BODY_PLURAL.get(b, b) for b in bodies]
    return (" and ".join(words))[:1].upper() + (" and ".join(words))[1:]


def rule_text(cfg) -> str:
    """How the list is built and ranked, from its config."""
    mk, f = cfg["market"], cfg.get("filters") or {}
    if cfg["metric"] == "markets_desc":
        return ("Cars on sale in at least one market in our data (US, Canada, EU, UK, China, Japan, South Korea, "
                "India, Australia) with no current US listing in our data, ranked by the number of markets they "
                "are on sale in, then by name.")
    cur = MARKET_CURRENCY.get(mk)
    clauses = []
    if f.get("max_price"):
        clauses.append("a published price under %s" % _money(f["max_price"], cur))
    if f.get("min_range"):
        clauses.append("a published %s range of %s %s or more" % (
            PRIMARY_RANGE_CYCLE[mk], _fmt_num(f["min_range"]), "mi" if mk in ("US", "CA") else "km"))
    if f.get("min_seats"):
        clauses.append("a trim seating %d or more" % f["min_seats"])
    if f.get("connector"):
        clauses.append("a %s charging port on file" % f["connector"])
    head = "%s on sale %s" % (_noun(cfg), _where(mk))
    if clauses:
        head += " with " + " and ".join(clauses)
    rank = {
        "price_asc": "lowest current published price in %s, cheapest first (launch-only and estimated prices "
                     "are left out)" % cur,
        "range_desc": "%s range, longest first" % PRIMARY_RANGE_CYCLE.get(mk),
        "accel_asc": "quickest published %s time, quickest first" % accel_label(mk),
        "dc_desc": "highest published DC charging peak, highest first",
    }[cfg["metric"]]
    txt = "%s, ranked by %s." % (head, rank)
    if cfg.get("include_upcoming"):
        txt += " Models not on sale yet follow, by their announced range."
    return txt


def _metric_missing(cfg) -> str:
    mk = cfg["market"]
    return {"price_asc": "no current published price in %s" % MARKET_IN.get(mk, mk),
            "range_desc": "no published %s range" % PRIMARY_RANGE_CYCLE.get(mk),
            "accel_asc": "no published %s time" % accel_label(mk),
            "dc_desc": "no published DC charging peak",
            "markets_desc": "no market listing"}[cfg["metric"]]


def _cars(n) -> str:
    return "%d car%s" % (n, "" if n == 1 else "s")


# ---------------------------------------------------------------- building

def _sort_key(metric, item):
    v = item["value"]
    name = (item["_name"].lower(), item["model"]["slug"])
    if metric in ("price_asc", "accel_asc"):
        return (v,) + name
    return (-v,) + name


def compute(cat, cfg) -> dict:
    """All qualifying items (before the limit) plus exclusion counts for one registry entry."""
    mk, metric, f = cfg["market"], cfg["metric"], cfg.get("filters") or {}
    bodies = f.get("body_style")
    bodies = (bodies if isinstance(bodies, tuple) else (bodies,)) if bodies else None
    items, upcoming, excluded, unknown = [], [], 0, {"price": 0, "range": 0, "seats": 0, "connector": 0}
    for m in cat.models.values():
        if not base_eligible(cat, m):
            continue
        if bodies and m["body_style"] not in bodies:
            continue
        if metric == "markets_desc":
            mkts = current_markets(cat, m)
            if not mkts or f["not_sold_in"] in mkts:
                continue
            us = market_status(cat, m, f["not_sold_in"])
            items.append({"model": cat.model_card(m), "value": len(mkts), "unit": "markets", "variant": None,
                          "markets": mkts, "us_status": us, "_name": display_name(
                              cat.makes[m["make_id"]]["catalog_name"], m["name"]), "fact": {"value": len(mkts)}})
            continue
        status = "current" if on_sale(cat, m, mk) else None
        if status is None and cfg.get("include_upcoming") and m["_status"] == "upcoming" \
                and market_status(cat, m, mk) == "upcoming":
            status = "upcoming"
        if status is None:
            continue
        facts = market_facts(cat, m, mk, allow_estimates=(status == "upcoming"))
        ok = True
        if f.get("max_price"):
            if not facts["price"]:
                unknown["price"] += 1
                ok = False
            elif facts["price"]["value"] >= f["max_price"]:
                continue
        if f.get("min_range"):
            if not facts["range"]:
                unknown["range"] += 1
                ok = False
            elif facts["range"]["value"] < f["min_range"]:
                continue
        if f.get("min_seats"):
            if not facts["seats"]:
                unknown["seats"] += 1
                ok = False
            elif facts["seats"]["value"] < f["min_seats"]:
                continue
        if f.get("connector"):
            if not facts["connectors"]:
                unknown["connector"] += 1
                ok = False
            elif f["connector"] not in facts["connectors"]:
                continue
        if not ok:
            continue
        fact = facts[{"price_asc": "price", "range_desc": "range", "accel_asc": "accel", "dc_desc": "dc"}[metric]]
        if fact is None and status == "current":
            excluded += 1
            continue
        item = {"model": cat.model_card(m, mk), "value": fact["value"] if fact else None,
                "unit": (fact.get("currency") or fact.get("unit")) if fact else None,
                "variant": fact["variant"] if fact else None, "status": status, "fact": fact,
                "_name": display_name(cat.makes[m["make_id"]]["catalog_name"], m["name"])}
        (items if status == "current" else upcoming).append(item)
    items.sort(key=lambda i: _sort_key(metric, i))
    upcoming.sort(key=lambda i: (i["value"] is None,) + _sort_key(metric, dict(i, value=i["value"] or 0)))
    return {"items": items, "upcoming": upcoming, "excluded": excluded, "unknown": unknown}


def _finish_item(cfg, it, rank) -> dict:
    fact, metric = it["fact"], cfg["metric"]
    out = {k: v for k, v in it.items() if not k.startswith("_") and k != "fact"}
    out["rank"] = rank
    out["name"] = it["_name"]
    if fact and fact.get("value") is not None:
        out["display"] = fact_display(metric, fact)
        out["qualifier"] = basis_text(fact) if metric in ("price_asc", "range_desc") else None
        out["basis"] = fact.get("basis")
        out["cycle"] = fact.get("cycle")
        out["model_year"] = fact.get("model_year")
        out["is_estimate"] = bool(fact.get("is_estimate"))
    else:
        out.update(display=None, qualifier=None, basis=None, cycle=None, model_year=None,
                   is_estimate=it.get("status") == "upcoming")
    if metric == "accel_asc" and fact:
        out["label"] = fact.get("label")
    return out


def _notes(cfg, shown) -> List[str]:
    mk, metric, out = cfg["market"], cfg["metric"], []
    if metric == "price_asc" or (cfg.get("filters") or {}).get("max_price"):
        out.append("Prices are list prices as published, before taxes, fees and incentives; each is labelled "
                   "with its basis.")
        if any((i.get("basis") or "") == "msrp_excl_destination" for i in shown) or (
                mk == "US" and metric != "price_asc"):
            out.append(PRICE_EXCL_NOTE)
    if metric == "range_desc" or (cfg.get("filters") or {}).get("min_range"):
        out.append(RANGE_NOTE % PRIMARY_RANGE_CYCLE.get(mk))
    if metric == "dc_desc":
        out.append(DC_NOTE)
    if cfg.get("include_upcoming") and any(i.get("status") == "upcoming" for i in shown):
        out.append(UPCOMING_NOTE)
    if mk:
        out.append("Figures come from the trims of each model's current version sold in %s." % MARKET_IN.get(mk, mk))
    return out


def _excluded(cfg, c) -> dict:
    mk = cfg["market"]
    n = c["excluded"]
    reason = None
    if n:
        one = n == 1
        match = (" that match%s this list" % ("es" if one else "")) if cfg.get("filters") else ""
        reason = "%s on sale %s%s %s %s and %s not ranked." % (
            _cars(n), _where(mk), match, "has" if one else "have", _metric_missing(cfg), "is" if one else "are")
    unknown = []
    f = cfg.get("filters") or {}
    u = c["unknown"]
    if u["price"]:
        unknown.append("%s on sale %s %s no published price, so we can't tell whether %s under %s." % (
            _cars(u["price"]), _where(mk), "has" if u["price"] == 1 else "have",
            "it is" if u["price"] == 1 else "they are", _money(f["max_price"], MARKET_CURRENCY[mk])))
    if u["range"]:
        unknown.append("%s on sale %s %s no published %s range, so we can't tell whether %s %s %s." % (
            _cars(u["range"]), _where(mk), "has" if u["range"] == 1 else "have", PRIMARY_RANGE_CYCLE[mk],
            "it reaches" if u["range"] == 1 else "they reach", _fmt_num(f["min_range"]), "mi" if mk in ("US", "CA") else "km"))
    if u["seats"]:
        unknown.append("%s on sale %s %s no seat count on file." % (
            _cars(u["seats"]), _where(mk), "has" if u["seats"] == 1 else "have"))
    if u["connector"]:
        unknown.append("%s on sale %s %s no charging port on file." % (
            _cars(u["connector"]), _where(mk), "has" if u["connector"] == 1 else "have"))
    return {"count": n, "reason": reason, "unknown": unknown}


def build_all(cat) -> Dict[str, dict]:
    """Every registry list, computed and gated, keyed by list key (memoised on the cached catalog)."""
    memo = getattr(cat, "derived", None)
    if memo is not None and "lists" in memo:
        return memo["lists"]
    out: Dict[str, dict] = {}
    for cfg in LISTS:
        c = compute(cat, cfg)
        limit = min(cfg["limit"], MAX_LIMIT)
        shown = (c["items"] + c["upcoming"])[:limit]
        out[cfg["key"]] = {"cfg": cfg, "all": c["items"], "upcoming": c["upcoming"], "shown": shown,
                           "ranked": len(c["items"]),
                           "excluded": _excluded(cfg, c), "indexable": True, "reason": None}
    _gate(out)
    for key, d in out.items():
        d["related"] = _related(out, key)
    if memo is not None:
        memo["lists"] = out
    return out


def _slugs(items, n=None) -> List[str]:
    return [i["model"]["slug"] for i in (items[:n] if n else items)]


def _gate(out):
    indexed = []
    for cfg in LISTS:
        d = out[cfg["key"]]
        f = cfg.get("filters") or {}
        on_sale_shown = [i for i in d["shown"] if i.get("status", "current") == "current"]
        if cfg["key"] in ESTABLISHED:
            # Long-standing URLs: keep them indexable; the gates apply to new lists only.
            d["reason"] = "%d ranked." % d["ranked"]
            indexed.append(cfg)
            continue
        if d["ranked"] < MIN_ITEMS:
            d["indexable"] = False
            d["reason"] = "Only %d ranked; at least %d are needed." % (d["ranked"], MIN_ITEMS)
            continue
        if f.get("max_price"):
            lower = [o for o in LISTS if o["market"] == cfg["market"] and o["metric"] == cfg["metric"]
                     and (o.get("filters") or {}).get("max_price", 0) < f["max_price"]
                     and (o.get("filters") or {}).get("max_price")
                     and {k: v for k, v in (o.get("filters") or {}).items() if k != "max_price"}
                     == {k: v for k, v in f.items() if k != "max_price"}]
            if lower:
                lo = max(lower, key=lambda o: o["filters"]["max_price"])
                diff = len(set(_slugs(on_sale_shown)) - set(_slugs(out[lo["key"]]["shown"])))
                if diff < CEILING_MIN_DIFF:
                    d["indexable"] = False
                    d["reason"] = "Differs from %s by %d model%s; at least %d are needed." % (
                        lo["key"], diff, "" if diff == 1 else "s", CEILING_MIN_DIFF)
                    continue
        top = _slugs(on_sale_shown, OVERLAP_TOP)
        clash = None
        for prev in indexed:
            if prev["market"] != cfg["market"]:
                continue
            other = set(_slugs([i for i in out[prev["key"]]["shown"] if i.get("status", "current") == "current"],
                               OVERLAP_TOP))
            share = len(set(top) & other) / float(len(top)) if top else 0
            if share >= OVERLAP_MAX:
                clash = (prev["key"], share)
                break
        if clash:
            d["indexable"] = False
            d["reason"] = "Top %d overlaps %s by %d%%; %d%% or more is too close." % (
                OVERLAP_TOP, clash[0], round(clash[1] * 100), round(OVERLAP_MAX * 100))
            continue
        if len(indexed) >= MAX_LISTS:
            d["indexable"] = False
            d["reason"] = "Beyond the cap of %d lists." % MAX_LISTS
            continue
        d["reason"] = "%d ranked." % d["ranked"]
        indexed.append(cfg)


def _related(out, key) -> List[dict]:
    cfg = out[key]["cfg"]
    same = [c for c in LISTS if c["key"] != key and c["market"] == cfg["market"] and out[c["key"]]["indexable"]]
    other = sorted([c for c in LISTS if c["key"] != key and c["market"] != cfg["market"]
                    and c["metric"] == cfg["metric"] and out[c["key"]]["indexable"]],
                   key=lambda c: bool(c.get("filters")))          # unfiltered lists first, then registry order
    firsts = []                                                   # then each other market's first list
    for c in LISTS:
        if out[c["key"]]["indexable"] and c["key"] != key and c["market"] not in [x["market"] for x in firsts] \
                and c["market"] != cfg["market"]:
            firsts.append(c)
    picked = []
    for c in same + other + firsts:
        if c not in picked:
            picked.append(c)
    return [summary(out, c["key"], with_related=False) for c in picked[:RELATED_MAX]]


def path_of(key) -> str:
    return "/best/%s" % key


def summary(out, key, with_related=True) -> dict:
    """Registry entry as listed by GET /catalog/lists."""
    d = out[key]
    cfg = d["cfg"]
    s = {"key": key, "path": path_of(key), "title": cfg["title"], "h1": cfg["h1"], "blurb": cfg["blurb"],
         "market": cfg["market"], "metric": cfg["metric"], "rule": rule_text(cfg), "count": len(d["shown"]),
         "ranked": d["ranked"], "indexable": d["indexable"], "reason": d["reason"]}
    if with_related:
        s["related"] = [{"key": r["key"], "path": r["path"], "title": r["title"]} for r in d["related"]]
    return s


def response(cat, key, limit=None) -> Optional[dict]:
    """Body of GET /catalog/best/{key} (existing fields kept: key, title, market, metric, items, count)."""
    out = build_all(cat)
    d = out.get(key)
    if d is None:
        return None
    cfg = d["cfg"]
    n = min(limit or cfg["limit"], MAX_LIMIT)
    items = [_finish_item(cfg, it, i) for i, it in enumerate((d["all"] + d["upcoming"])[:n], 1)]
    return {"key": key, "path": path_of(key), "title": cfg["title"], "h1": cfg["h1"], "blurb": cfg["blurb"],
            "market": cfg["market"], "metric": OLD_METRIC[cfg["metric"]], "ranking": cfg["metric"],
            "rule": rule_text(cfg), "items": items, "count": len(items), "ranked": d["ranked"],
            "excluded": d["excluded"], "indexable": d["indexable"], "reason": d["reason"],
            "related": [{"key": r["key"], "path": r["path"], "title": r["title"], "market": r["market"]}
                        for r in d["related"]],
            "notes": _notes(cfg, items)}


def ranks_of(cat, model_slug) -> List[dict]:
    """Indexable lists a model is shown in: [{key, title, path, rank, count, market}] in registry order."""
    out = build_all(cat)
    res = []
    for cfg in LISTS:
        d = out[cfg["key"]]
        if not d["indexable"]:
            continue
        for i, it in enumerate(d["shown"], 1):
            if it["model"]["slug"] == model_slug:
                res.append({"key": cfg["key"], "title": cfg["title"], "path": path_of(cfg["key"]),
                            "rank": i, "count": len(d["shown"]), "market": cfg["market"]})
                break
    return res
