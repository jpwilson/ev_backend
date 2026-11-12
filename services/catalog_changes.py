"""Version-change pages: what changed between two adjacent generations of a model.

Pure functions over the dicts a Catalog (services/catalog_service.py) has already loaded:
generations and variants carry their effective '_status'; offerings are the raw
variant_markets rows. No database access here.

Rules (FEATURES_BRIEF.md, feature 1):
  - Pairs: adjacent non-cancelled generations ordered by generation_sort_key, older first.
  - Values are never converted. Two values are compared only inside one comparability group:
    price = (market, currency, price_basis), range = (market, unit, cycle), battery = battery_basis.
    Per variant the newest model year with a value in the chosen group is used.
  - Everything a reader sees is templated from data; words stay neutral (no "better", no "new").
"""
import re
from typing import Callable, Dict, List, Optional, Tuple

import services.catalog_status as S
from services.catalog_service import MARKETS, MARKET_PREFERENCE, PRIMARY_RANGE_CYCLE, _iso, _num, _variant_order

MIN_COMPARABLE_FACTS = 3

MARKET_IN = {"US": "the US", "CA": "Canada", "EU": "the EU", "UK": "the UK", "CN": "China", "JP": "Japan",
             "KR": "South Korea", "IN": "India", "AU": "Australia"}
MARKET_SHORT = {"US": "US", "CA": "Canada", "EU": "EU", "UK": "UK", "CN": "China", "JP": "Japan",
                "KR": "South Korea", "IN": "India", "AU": "Australia"}
PRICE_BASIS_TEXT = {"msrp_excl_destination": "MSRP excluding destination",
                    "msrp_incl_destination": "MSRP including destination",
                    "list_incl_vat": "list price including VAT"}
CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£"}

PRICE_NOTE = "List prices are as published, not adjusted for inflation."
ESTIMATE_NOTE = "Figures marked as manufacturer estimates are targets announced before sale."
BATTERY_UNKNOWN = "The source doesn't say whether these are gross or usable."

# key, label, source, field, aggregate, unit, (word when newer is larger, word when smaller)
NUMBER_ROWS = (
    ("entry_price", "Entry price", "price", None, "min", None, ("higher", "lower")),
    ("longest_range", "Longest range", "range", None, "max", None, ("longer", "shorter")),
    ("largest_battery", "Largest battery", "battery", "battery_kwh", "max", "kWh", ("larger", "smaller")),
    ("most_power", "Most power", "spec", "power_hp", "max", "hp", ("more", "less")),
    ("quickest_0_60", "Quickest 0–60 mph", "spec", "accel_0_60_s", "min", "s", ("slower", "quicker")),
    ("quickest_0_100", "Quickest 0–100 km/h", "spec", "accel_0_100_s", "min", "s", ("slower", "quicker")),
    ("top_speed", "Highest top speed", "spec", "top_speed_mph", "max", "mph", ("higher", "lower")),
    ("fastest_dc", "Fastest DC charging peak", "spec", "dc_kw", "max", "kW", ("higher", "lower")),
)
NUMBER_ROW = {r[0]: r for r in NUMBER_ROWS}
TRIM_ROWS = ("entry_price", "longest_range", "largest_battery", "most_power", "quickest_0_60",
             "quickest_0_100", "top_speed", "fastest_dc")
# labels for one matched trim against its counterpart (no "largest"/"quickest": one value per side)
TRIM_LABEL = {"entry_price": "Price", "longest_range": "Range", "largest_battery": "Battery",
              "most_power": "Power", "quickest_0_60": "0–60 mph", "quickest_0_100": "0–100 km/h",
              "top_speed": "Top speed", "fastest_dc": "DC charging peak"}
# phrase used in the summary / FAQ: "the {phrase} went from X to Y"
SUMMARY_PHRASE = {"entry_price": "entry price", "longest_range": "longest range",
                  "largest_battery": "largest battery", "most_power": "highest power output",
                  "quickest_0_60": "quickest 0–60 mph time", "quickest_0_100": "quickest 0–100 km/h time",
                  "top_speed": "highest top speed", "fastest_dc": "fastest DC charging peak"}
COMPARED = ("increased", "decreased", "unchanged")


# ---------------------------------------------------------------- formatting

def _fmt_num(x) -> str:
    x = _num(x)
    if isinstance(x, float):
        if x.is_integer():
            x = int(x)
        else:
            return format(round(x, 2), ",.2f").rstrip("0").rstrip(".")
    return format(x, ",")


def _money(value, currency) -> str:
    sym = CURRENCY_SYMBOL.get(currency or "")
    return "%s%s" % (sym, _fmt_num(value)) if sym else "%s %s" % (currency or "", _fmt_num(value))


def years_text(gen) -> str:
    a, b, st = gen.get("start_year"), gen.get("end_year"), gen.get("_status")
    if a and b:
        return str(a) if a == b else "%d–%d" % (a, b)
    if a and st == "current":
        return "%d–present" % a
    if a:
        return "from %d" % a
    if b:
        return "until %d" % b
    return ""


def _span_text(span) -> str:
    if not span:
        return ""
    a, b = span["from"], span["to"]
    return str(a) if a == b else "%d–%d" % (a, b)


# ---------------------------------------------------------------- pairs

def live_generations(gens: List[dict]) -> List[dict]:
    """Non-cancelled generations, oldest first."""
    return sorted([g for g in gens if g.get("_status") != "cancelled"], key=S.generation_sort_key)


def adjacent_pairs(gens: List[dict]) -> List[Tuple[dict, dict]]:
    """(older, newer) for each pair of neighbouring non-cancelled generations, oldest pair first."""
    live = live_generations(gens)
    return list(zip(live, live[1:]))


def find_pair(gens: List[dict], a_slug: str, b_slug: str) -> Optional[Tuple[dict, dict]]:
    """The adjacent pair named by two generation slugs in either order, or None."""
    a_slug, b_slug = (a_slug or "").lower(), (b_slug or "").lower()
    for older, newer in adjacent_pairs(gens):
        if {older["slug"], newer["slug"]} == {a_slug, b_slug} and a_slug != b_slug:
            return older, newer
    return None


# ---------------------------------------------------------------- trims

def _norm(name: Optional[str]) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split())


def _paren(name: Optional[str]) -> Optional[str]:
    """'Premium AWD (Long Range AWD)' -> 'long range awd'."""
    m = re.match(r"^.*\(([^()]+)\)\s*$", name or "")
    return _norm(m.group(1)) if m else None


def _same_slug(a, b):
    return bool(a.get("variant_slug")) and a.get("variant_slug") == b.get("variant_slug")


def _same_name(a, b):
    na = _norm(a.get("variant_name"))
    return bool(na) and na == _norm(b.get("variant_name"))


def _alias(a, b):
    pa, pb = _paren(a.get("variant_name")), _paren(b.get("variant_name"))
    return bool((pa and pa == _norm(b.get("variant_name"))) or (pb and pb == _norm(a.get("variant_name"))))


def _drivetrain_conflict(a, b) -> bool:
    da, db = a.get("drivetrain"), b.get("drivetrain")
    return bool(da and db and da != db)


def live_variants(variants: List[dict]) -> List[dict]:
    """Non-cancelled variants in seed order (all of them if every one is cancelled)."""
    live = [v for v in variants if v.get("_status") != "cancelled"] or list(variants)
    return sorted(live, key=_variant_order)


def match_trims(older: List[dict], newer: List[dict]):
    """Strict one-to-one trim matching: same slug, then same normalised name, then a parenthesised
    alias equal to the other side's name. A step matches only when the pair is unique on both sides,
    and never when both drivetrains are set and differ.
    Returns (matched [(older, newer, how)], only_older, only_newer)."""
    left, right = list(older), list(newer)
    matched = []
    for how, same in (("slug", _same_slug), ("name", _same_name), ("alias", _alias)):
        for a in list(left):
            cands = [b for b in right if same(a, b)]
            if len(cands) != 1:
                continue
            b = cands[0]
            if len([x for x in left if same(x, b)]) != 1 or _drivetrain_conflict(a, b):
                continue
            matched.append((a, b, how))
            left.remove(a)
            right.remove(b)
    return matched, left, right


# ---------------------------------------------------------------- values

def _offers_in(side, v, market):
    return [o for o in side["offers"].get(v["id"], []) if o.get("market") == market]


def _newest_first(offers):
    return sorted(offers, key=lambda o: (o.get("model_year") is None, -(o.get("model_year") or 0)))


def _price_of(o):
    if o.get("current_price") is not None:
        return o["current_price"], "price"
    if o.get("launch_price") is not None:
        return o["launch_price"], "launch"
    return None, None


def _group_ok(source, g) -> bool:
    """A group whose qualifiers are all recorded (a null basis counts for battery: flagged instead)."""
    if source in ("price", "range"):
        return all(x is not None for x in g)
    return True


def _candidates(side, source, field, market, variants) -> Dict[tuple, list]:
    """{group: [cand]} where cand = dict(value, variant, offer, price_kind); one cand per variant per group."""
    out: Dict[tuple, list] = {}
    for v in variants:
        if source in ("price", "range"):
            if not market:
                continue
            seen = set()
            for o in _newest_first(_offers_in(side, v, market)):
                if source == "price":
                    val, kind = _price_of(o)
                    g = (o.get("market"), o.get("currency"), o.get("price_basis"))
                else:
                    val, kind = o.get("range_value"), None
                    g = (o.get("market"), o.get("range_unit"), o.get("range_cycle"))
                if val is None or g in seen:
                    continue
                seen.add(g)
                out.setdefault(g, []).append({"value": _num(val), "variant": v, "offer": o, "price_kind": kind})
        else:
            val = v.get(field)
            if val is None:
                continue
            g = (v.get("battery_basis"),) if source == "battery" else ("spec",)
            out.setdefault(g, []).append({"value": _num(val), "variant": v, "offer": None, "price_kind": None})
    return out


def _group_rank(source, market, g, cands_lists):
    """Higher is preferred: the market's primary cycle, a stated battery basis, more values, newest year."""
    n = sum(len(c) for c in cands_lists)
    years = [c["offer"].get("model_year") or 0 for cs in cands_lists for c in cs if c["offer"]]
    pref = 0
    if source == "range" and g[2] == PRIMARY_RANGE_CYCLE.get(market):
        pref = 1
    if source == "battery" and g[0] is not None:
        pref = 1
    return (pref, n, max(years) if years else 0, str(g))


def _pick(cands, agg):
    if not cands:
        return None
    best = cands[0]
    for c in cands[1:]:
        if (agg == "min" and c["value"] < best["value"]) or (agg == "max" and c["value"] > best["value"]):
            best = c
    return best


def _side_obj(c, source, unit, side, mini) -> Optional[dict]:
    if c is None:
        return None
    o, v = c["offer"], c["variant"]
    est = bool(side.get("upcoming")) or v.get("_status") == "upcoming" or bool(o and o.get("is_estimate"))
    d = {"value": c["value"], "unit": unit, "cycle": None, "market": None, "model_year": None,
         "price_kind": None, "basis": None, "is_estimate": est, "variant": mini(v)}
    if source == "price":
        d.update(unit=o.get("currency"), market=o.get("market"), model_year=o.get("model_year"),
                 price_kind=c["price_kind"], basis=o.get("price_basis"))
    elif source == "range":
        d.update(unit=o.get("range_unit"), cycle=o.get("range_cycle"), market=o.get("market"),
                 model_year=o.get("model_year"))
    elif source == "battery":
        d["basis"] = v.get("battery_basis")
    return d


def _reason(source, go, gn) -> str:
    if source == "price":
        if None in go or None in gn:
            return "the price basis or currency isn't recorded for one of them"
        if go[1] != gn[1]:
            return "the prices are in different currencies (%s vs %s)" % (go[1], gn[1])
        return "the prices are on different bases (%s vs %s)" % (
            PRICE_BASIS_TEXT.get(go[2], go[2]), PRICE_BASIS_TEXT.get(gn[2], gn[2]))
    if source == "range":
        if None in go or None in gn:
            return "the test cycle isn't recorded for one of them"
        if go[2] != gn[2]:
            return "the ranges are from different test cycles (%s vs %s)" % (go[2], gn[2])
        return "the ranges are in different units (%s vs %s)" % (go[1], gn[1])
    if source == "battery":
        if go[0] is None or gn[0] is None:
            return "only one of them states whether the capacity is gross or usable"
        return "the capacities are stated on different bases (%s vs %s)" % (go[0], gn[0])
    return "not comparable"


def _delta(a, b):
    d = round(float(b) - float(a), 2)
    return int(d) if d.is_integer() else d


def compare_number(key, older, newer, market, mini, trim=False) -> Optional[dict]:
    """One numeric row for two sides (each side: gen, variants in scope, offers, upcoming).
    trim=True: each side's scope is one matched trim (plain labels)."""
    _, label, source, field, agg, unit, _ = NUMBER_ROW[key]
    if trim:
        label = TRIM_LABEL[key]
    co = _candidates(older, source, field, market, older["scope"])
    cn = _candidates(newer, source, field, market, newer["scope"])
    if not co and not cn:
        return None
    shared = [g for g in co if g in cn and _group_ok(source, g)]
    row = {"key": key, "label": label, "kind": "number", "older": None, "newer": None,
           "change": {"status": None, "delta": None, "unit": None, "reason": None}}
    if shared:
        g = max(shared, key=lambda g: _group_rank(source, market, g, [co[g], cn[g]]))
        go = gn = g
    else:
        go = max(co, key=lambda g: _group_rank(source, market, g, [co[g]])) if co else None
        gn = max(cn, key=lambda g: _group_rank(source, market, g, [cn[g]])) if cn else None
    row["older"] = _side_obj(_pick(co.get(go, []), agg) if go else None, source, unit, older, mini)
    row["newer"] = _side_obj(_pick(cn.get(gn, []), agg) if gn else None, source, unit, newer, mini)
    ch = row["change"]
    if row["older"] is None:
        ch["status"] = "missing_older"
    elif row["newer"] is None:
        ch["status"] = "missing_newer"
    elif not shared:
        ch["status"] = "not_comparable"
        ch["reason"] = _reason(source, go, gn)
    else:
        a, b = row["older"]["value"], row["newer"]["value"]
        d = _delta(a, b)
        ch.update(status="unchanged" if d == 0 else ("increased" if d > 0 else "decreased"),
                  delta=d, unit=row["newer"]["unit"])
        if source == "battery" and go[0] is None:
            ch["basis_unknown"] = True
            ch["reason"] = BATTERY_UNKNOWN
    return row


def _set_side(values, side) -> Optional[dict]:
    if not values:
        return None
    return {"value": values, "unit": None, "cycle": None, "market": None, "model_year": None,
            "price_kind": None, "basis": None, "is_estimate": bool(side.get("upcoming")), "variant": None}


def _ordered(values):
    return sorted(values, key=lambda x: (str(type(x)), x))


def compare_set(key, label, older_vals, newer_vals, older, newer, market=None) -> Optional[dict]:
    if not older_vals and not newer_vals:
        return None
    ov, nv = _ordered(set(older_vals)), _ordered(set(newer_vals))
    row = {"key": key, "label": label, "kind": "set", "older": _set_side(ov, older), "newer": _set_side(nv, newer),
           "change": {"status": None, "delta": None, "unit": None, "reason": None}}
    for s in (row["older"], row["newer"]):
        if s:
            s["market"] = market
    if not ov:
        row["change"]["status"] = "missing_older"
    elif not nv:
        row["change"]["status"] = "missing_newer"
    elif ov == nv:
        row["change"]["status"] = "unchanged"
    else:
        row["change"].update(status="changed", added=[x for x in nv if x not in ov],
                             removed=[x for x in ov if x not in nv])
    return row


def model_years(side, market=None) -> Dict[str, dict]:
    """{market: {from, to}} over the side's live variants' offerings (model_year known)."""
    out: Dict[str, list] = {}
    for v in side["live"]:
        for o in side["offers"].get(v["id"], []):
            if o.get("model_year") is not None and (market is None or o.get("market") == market):
                out.setdefault(o["market"], []).append(o["model_year"])
    order = lambda k: MARKETS.index(k) if k in MARKETS else 99  # noqa: E731
    return {k: {"from": min(ys), "to": max(ys)} for k, ys in sorted(out.items(), key=lambda kv: order(kv[0]))}


def side(gen: dict, variants: List[dict], offers: Dict[int, list], market: Optional[str]) -> dict:
    """The data one generation contributes for one market."""
    live = live_variants(variants)
    s = {"gen": gen, "live": live, "offers": offers, "upcoming": gen.get("_status") == "upcoming"}
    s["markets"] = {o.get("market") for v in live for o in offers.get(v["id"], []) if o.get("market")}
    if market and market in s["markets"]:
        # trims sold there, plus trims with no offering anywhere (not tied to a market)
        s["scope"] = [v for v in live if not offers.get(v["id"]) or _offers_in(s, v, market)]
    else:
        s["scope"] = live
    return s


def _default_mini(v):
    return {"id": v.get("id"), "slug": v.get("variant_slug"), "name": v.get("variant_name")}


def diff(older: dict, newer: dict, market: Optional[str], mini: Callable = _default_mini) -> List[dict]:
    """All rows for one market. `older`/`newer` come from side()."""
    rows = []
    for key in ("entry_price", "longest_range", "largest_battery", "most_power"):
        rows.append(compare_number(key, older, newer, market, mini))
    for key in ("quickest_0_60", "quickest_0_100", "top_speed", "fastest_dc"):
        rows.append(compare_number(key, older, newer, market, mini))

    def offer_set(s, field):
        if not market:
            return []
        return [o.get(field) for v in s["scope"] for o in _offers_in(s, v, market) if o.get(field)]
    rows.append(compare_set("connector", "Charging connector", offer_set(older, "connector"),
                            offer_set(newer, "connector"), older, newer, market))
    rows.append(compare_set("drivetrains", "Drivetrains", [v["drivetrain"] for v in older["scope"] if v.get("drivetrain")],
                            [v["drivetrain"] for v in newer["scope"] if v.get("drivetrain")], older, newer))
    rows.append(compare_set("seats", "Seats", [v["seats"] for v in older["scope"] if v.get("seats")],
                            [v["seats"] for v in newer["scope"] if v.get("seats")], older, newer))
    # trims on file (all markets) - informational, never counted as a comparable fact
    no, nn = len(older["live"]), len(newer["live"])
    if no or nn:
        d = nn - no
        rows.append({"key": "trims", "label": "Trims on file", "kind": "count",
                     "older": dict(_set_side([1], older) or {}, value=no, unit="trims") if no else None,
                     "newer": dict(_set_side([1], newer) or {}, value=nn, unit="trims") if nn else None,
                     "change": {"status": ("missing_older" if not no else "missing_newer" if not nn else
                                           "unchanged" if d == 0 else "increased" if d > 0 else "decreased"),
                                "delta": d if no and nn else None, "unit": "trims", "reason": None}})
    if market:
        so, sn = model_years(older, market).get(market), model_years(newer, market).get(market)
        if so or sn:
            def span_side(sp, s):
                if not sp:
                    return None
                return dict(_set_side([1], s), value=_span_text(sp), market=market, **{"from": sp["from"], "to": sp["to"]})
            rows.append({"key": "model_years", "label": "Model years on file", "kind": "span",
                         "older": span_side(so, older), "newer": span_side(sn, newer),
                         "change": {"status": "missing_older" if not so else "missing_newer" if not sn else "info",
                                    "delta": None, "unit": None, "reason": None}})
    return [r for r in rows if r is not None]


def is_comparable(row) -> bool:
    return (row["kind"] == "number" and row["change"]["status"] in COMPARED
            and not row["change"].get("basis_unknown"))


def comparable_facts(rows) -> int:
    return sum(1 for r in rows if is_comparable(r))


def candidate_markets(older: dict, newer: dict) -> List[str]:
    order = lambda k: MARKET_PREFERENCE.index(k) if k in MARKET_PREFERENCE else 99  # noqa: E731
    both = older["markets"] & newer["markets"]
    return sorted(both or (older["markets"] | newer["markets"]), key=order)


def pick_market(gen_o, vars_o, gen_n, vars_n, offers) -> Optional[str]:
    """US when both sides have US offerings; else the market with most comparable facts
    (ties by MARKET_PREFERENCE); None when neither side has any offering."""
    so, sn = side(gen_o, vars_o, offers, None), side(gen_n, vars_n, offers, None)
    if "US" in so["markets"] and "US" in sn["markets"]:
        return "US"
    best, best_n = None, -1
    for mk in candidate_markets(so, sn):  # already in preference order: first max wins ties
        n = comparable_facts(diff(side(gen_o, vars_o, offers, mk), side(gen_n, vars_n, offers, mk), mk))
        if n > best_n:
            best, best_n = mk, n
    return best


# ---------------------------------------------------------------- text

def gen_labels(older, newer) -> Tuple[str, str]:
    a, b = older.get("name") or older["slug"], newer.get("name") or newer["slug"]
    if _norm(a) == _norm(b):
        a, b = "%s (%s)" % (a, older["slug"]), "%s (%s)" % (b, newer["slug"])
    return a, b


def fmt_value(row, s) -> str:
    """'363 mi (EPA)', '$36,990', '84 kWh', 'CCS1, NACS', '2017-2023'."""
    key, v = row["key"], s["value"]
    if row["kind"] in ("set",):
        return ", ".join(str(x) for x in v)
    if row["kind"] in ("span",):
        return v
    if key == "entry_price":
        return _money(v, s["unit"])
    if key == "longest_range":
        return "%s %s" % (_fmt_num(v), s["unit"])
    if key == "trims":
        return str(v)
    return "%s %s" % (_fmt_num(v), s["unit"] or "")


def _trim_name(v) -> str:
    """Trim name for use inside parentheses: 'Premium RWD [Long Range RWD]'."""
    return (v.get("name") or v.get("slug") or "").replace("(", "[").replace(")", "]")


def _provenance(row, s, trim=False) -> str:
    """'(Premium RWD, 2026 model year, launch price, manufacturer estimate)' or ''."""
    if row["kind"] != "number":
        return " (manufacturer estimate)" if s.get("is_estimate") and row["kind"] == "set" else ""
    bits = []
    if s.get("variant") and not trim:
        bits.append(_trim_name(s["variant"]))
    if s.get("model_year"):
        bits.append("%d model year" % s["model_year"])
    if s.get("price_kind") == "launch":
        bits.append("launch price")
    if row["key"] == "entry_price" and row["change"]["status"] == "not_comparable" and s.get("basis"):
        bits.append(PRICE_BASIS_TEXT.get(s["basis"], s["basis"]))
    if row["key"] == "longest_range" and row["change"]["status"] == "not_comparable":
        bits.append(s.get("cycle") or "test cycle not recorded")
    if row["key"] == "largest_battery" and row["change"]["status"] == "not_comparable":
        bits.append(s.get("basis") or "basis not stated")
    if s.get("is_estimate"):
        bits.append("manufacturer estimate")
    return " (%s)" % ", ".join(bits) if bits else ""


def row_qualifier(row, market) -> str:
    """Qualifiers that hold for both sides: 'US, MSRP excluding destination' ('' when none)."""
    o, n = row["older"], row["newer"]
    s = o or n
    q = []
    if row["key"] in ("entry_price", "longest_range", "connector", "model_years") and market:
        q.append(MARKET_SHORT.get(market, market))
    if row["change"]["status"] != "not_comparable":
        if row["key"] == "entry_price" and s.get("basis"):
            q.append(PRICE_BASIS_TEXT.get(s["basis"], s["basis"]))
        if row["key"] == "longest_range" and s.get("cycle"):
            q.append(s["cycle"])
        if row["key"] == "largest_battery" and s.get("basis"):
            q.append(s["basis"])
    return ", ".join(q)


def row_label(row, market) -> str:
    """'Entry price (US, MSRP excluding destination)'."""
    q = row_qualifier(row, market)
    return "%s (%s)" % (row["label"], q) if q else row["label"]


def delta_text(row) -> str:
    key, ch = row["key"], row["change"]
    up, down = NUMBER_ROW[key][6] if key in NUMBER_ROW else ("more", "fewer")
    d = abs(ch["delta"])
    word = up if ch["delta"] > 0 else down
    if key == "entry_price":
        return "%s %s" % (_money(d, ch["unit"]), word)
    unit = "trim" if ch["unit"] == "trims" and d == 1 else ch["unit"]
    return "%s %s %s" % (_fmt_num(d), unit, word)


def row_text(row, labels, market, trim=False) -> str:
    O, N = labels

    def provenance(r, s):
        return _provenance(r, s, trim)
    o, n, st = row["older"], row["newer"], row["change"]["status"]
    head = row_label(row, market)
    if row["kind"] == "span":
        if st == "info":
            return "%s: %s for the %s; %s for the %s." % (head, o["value"], O, n["value"], N)
    if st == "missing_older":
        return "%s: %s%s in the %s. Not on file for the %s." % (head, fmt_value(row, n), provenance(row, n), N, O)
    if st == "missing_newer":
        return "%s: %s%s in the %s. Not on file for the %s." % (head, fmt_value(row, o), provenance(row, o), O, N)
    if st == "not_comparable":
        return "%s: %s%s in the %s; %s%s in the %s. Not compared: %s." % (
            head, fmt_value(row, o), provenance(row, o), O, fmt_value(row, n), provenance(row, n), N,
            row["change"]["reason"])
    if st == "unchanged":
        if row["kind"] == "number":
            txt = "%s: %s in both the %s%s and the %s%s." % (
                head, fmt_value(row, o), O, provenance(row, o), N, provenance(row, n))
        else:
            txt = "%s: %s in both." % (head, fmt_value(row, o))
    elif st == "changed":
        txt = "%s: %s in the %s; %s in the %s." % (head, fmt_value(row, o), O, fmt_value(row, n), N)
    else:
        txt = "%s: %s%s in the %s vs %s%s in the %s, %s." % (
            head, fmt_value(row, o), provenance(row, o), O, fmt_value(row, n), provenance(row, n), N,
            delta_text(row))
    if row["change"].get("basis_unknown"):
        txt += " " + BATTERY_UNKNOWN
    return txt


def _went(row) -> str:
    """'the longest EPA range went from 358 mi to 363 mi'."""
    o, n, key = row["older"], row["newer"], row["key"]
    phrase = SUMMARY_PHRASE[key]
    if key == "longest_range" and o.get("cycle"):
        phrase = "longest %s range" % o["cycle"]
    if key == "entry_price" and o.get("basis"):
        phrase = "entry price (%s)" % PRICE_BASIS_TEXT.get(o["basis"], o["basis"])
    if key == "largest_battery" and o.get("basis"):
        phrase = "largest battery (%s)" % o["basis"]

    def p(s):
        if key == "entry_price":
            text = _money(s["value"], s["unit"])
        else:
            text = "%s %s" % (_fmt_num(s["value"]), s["unit"])
        extra = []
        if key == "entry_price" and s.get("model_year"):
            extra.append("%d model year" % s["model_year"])
        if s.get("price_kind") == "launch":
            extra.append("launch price")
        if s.get("is_estimate"):
            extra.append("manufacturer estimate")
        return text + (" (%s)" % ", ".join(extra) if extra else "")
    return "the %s went from %s to %s" % (phrase, p(o), p(n))


def _relative(row) -> float:
    a = abs(float(row["older"]["value"])) or 1.0
    return abs(float(row["change"]["delta"])) / a


def top_changes(rows, n=3) -> List[dict]:
    changed = [r for r in rows if is_comparable(r) and r["change"]["status"] != "unchanged"]
    return sorted(changed, key=_relative, reverse=True)[:n]


def _join(parts: List[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    if len(parts) == 2:
        return "%s and %s" % tuple(parts)
    return "; ".join(parts[:-1]) + "; and " + parts[-1]


def _and(values) -> str:
    """'AWD', 'AWD and RWD', 'CCS1, CCS2 and NACS'."""
    vals = [str(v) for v in values]
    return vals[0] if len(vals) == 1 else "%s and %s" % (", ".join(vals[:-1]), vals[-1])


def display_name(make_name: Optional[str], model_name: str) -> str:
    """'Kia EV6'; a model name that already starts with the make is kept ('Polestar 2')."""
    if not make_name or _norm(model_name).startswith(_norm(make_name)):
        return model_name
    return "%s %s" % (make_name, model_name)


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def summary(model_name, older, newer, relation, rows, market, labels) -> List[str]:
    O, N = labels
    by = {r["key"]: r for r in rows}
    if relation == "refresh":
        verb = "is an upcoming refresh of" if newer.get("_status") == "upcoming" else "is a refresh of"
    elif newer.get("_status") == "upcoming":
        verb = "is the upcoming successor to"
    elif older.get("_status") == "current":
        verb = "is the successor to"
    else:
        verb = "replaced"
    yn, yo = years_text(newer), years_text(older)
    def yrs(name, y, mid):
        if not y:
            return ""
        if "(" in name:   # 'Second generation (Yuan Plus), 2026–present,' instead of nested parentheses
            return ", %s%s" % (y, "," if mid else "")
        return " (%s)" % y
    out = ["%s %s%s %s the %s%s." % (model_name, N, yrs(N, yn, True), verb, O, yrs(O, yo, False))]
    if newer.get("_status") == "upcoming":
        if any(r.get("newer") for r in rows if r["kind"] == "number"):
            out.append("The %s is not on sale yet; its figures are manufacturer estimates." % N)
        else:
            out.append("The %s is not on sale yet." % N)
    top = top_changes(rows)
    if top:
        where = " in %s" % MARKET_IN.get(market, market) if market else ""
        out.append(_cap("Largest change%s on file%s: %s." % ("s" if len(top) > 1 else "", where,
                                                           _join([_went(r) for r in top]))))
    mk = MARKET_SHORT.get(market, market) if market else None
    for key, noun in (("entry_price", "price"), ("longest_range", "range")):
        r = by.get(key)
        st = r["change"]["status"] if r else None
        if st in COMPARED:
            continue
        if not market:
            out.append("No %s is on file for either version." % noun)
        elif r is None:
            out.append("No %s %s is on file for either version." % (mk, noun))
        elif st == "missing_older":
            out.append("No %s %s is on file for the %s." % (mk, noun, O))
        elif st == "missing_newer":
            out.append("No %s %s is on file for the %s." % (mk, noun, N))
        elif st == "not_comparable":
            out.append("%s %ss are on file for both, but %s, so they are not compared." % (
                mk, noun, r["change"]["reason"]))
    return out


def faq(model_name, rows, market, labels, years_by_side, trims_only=((), ())) -> List[dict]:
    O, N = labels
    by = {r["key"]: r for r in rows}
    out = []
    changes = [r for r in rows if is_comparable(r) and r["change"]["status"] != "unchanged"]
    changes.sort(key=_relative, reverse=True)
    set_changes = [r for r in rows if r["kind"] == "set" and r["change"]["status"] == "changed"]
    if changes or set_changes:
        parts = [_went(r) for r in changes]
        nouns = {"connector": "charging connector", "drivetrains": "drivetrains offered", "seats": "seat counts"}
        for r in set_changes:
            parts.append("the %s went from %s to %s" % (
                nouns[r["key"]], _and(r["older"]["value"]), _and(r["newer"]["value"])))
        where = "Comparing %s data: " % MARKET_SHORT.get(market, market) if market else ""
        a = "%s%s." % (where, _join(parts))
        only_o, only_n = trims_only
        if only_o:
            a += " Trims only in the %s: %s." % (O, ", ".join(_trim_name(v) for v in only_o))
        if only_n:
            a += " Trims only in the %s: %s." % (N, ", ".join(_trim_name(v) for v in only_n))
        out.append({"q": "What changed between the %s %s and the %s?" % (model_name, O, N), "a": _cap(a)})

    def yes_no(key, q, more, less, same, closing=""):
        r = by.get(key)
        if not r or not is_comparable(r):
            return
        o, n = r["older"], r["newer"]
        lead = {"increased": more, "decreased": less, "unchanged": same}[r["change"]["status"]]
        a = "%s %s%s in the %s vs %s%s in the %s.%s" % (
            lead, fmt_value(r, n), _provenance(r, n), N, fmt_value(r, o), _provenance(r, o), O, closing)
        out.append({"q": q, "a": a})

    rl = by.get("longest_range")
    if rl and is_comparable(rl):
        what = "longest %s range on file%s" % (rl["older"]["cycle"],
                                              " in %s" % MARKET_IN.get(market, market) if market else "")
        yes_no("longest_range", "Does the %s %s have more range than the %s?" % (model_name, N, O),
               "Yes. The %s is" % what, "No. The %s is" % what, "No. The %s is the same:" % what)
    rp = by.get("entry_price")
    if rp and is_comparable(rp):
        basis = PRICE_BASIS_TEXT.get(rp["older"]["basis"], rp["older"]["basis"])
        what = "lowest %s on file%s" % (basis, " in %s" % MARKET_IN.get(market, market) if market else "")
        yes_no("entry_price", "Is the %s %s more expensive than the %s?" % (model_name, N, O),
               "Yes. The %s is" % what, "No. The %s is" % what, "No. The %s is the same:" % what,
               " " + PRICE_NOTE)
    spans_o, spans_n = years_by_side
    common = [mk for mk in spans_o if mk in spans_n]
    if common:
        parts = ["in %s, %s %s the %s and %s %s the %s" % (
            MARKET_IN.get(mk, mk), _span_text(spans_o[mk]), "is" if spans_o[mk]["from"] == spans_o[mk]["to"] else "are",
            O, _span_text(spans_n[mk]), "is" if spans_n[mk]["from"] == spans_n[mk]["to"] else "are", N)
            for mk in common]
        out.append({"q": "Which model years are the %s %s and which are the %s?" % (model_name, O, N),
                    "a": _cap("Model years on file: %s." % "; ".join(parts))})
    peak = "The fastest DC charging peak (maximum power) on file is"
    yes_no("fastest_dc", "Does the %s %s charge faster than the %s?" % (model_name, N, O),
           "%s higher:" % peak, "%s lower:" % peak, "%s the same:" % peak)
    return out


# ---------------------------------------------------------------- page

def pair_path(cat, m, older, newer) -> str:
    return "%s/changes/%s-vs-%s" % (cat.model_path(m), older["slug"], newer["slug"])


def pair_sides(cat, older, newer, market):
    return (side(older, cat.variants_by_gen[older["id"]], cat.offerings, market),
            side(newer, cat.variants_by_gen[newer["id"]], cat.offerings, market))


def pair_markets(cat, older, newer) -> List[str]:
    """Markets where either generation has an offering, in MARKETS order (the market picker)."""
    so, sn = pair_sides(cat, older, newer, None)
    return sorted(so["markets"] | sn["markets"], key=lambda k: MARKETS.index(k) if k in MARKETS else 99)


def default_market(cat, older, newer) -> Optional[str]:
    return pick_market(older, cat.variants_by_gen[older["id"]], newer, cat.variants_by_gen[newer["id"]],
                       cat.offerings)


def pair_quality(cat, older, newer) -> dict:
    """{market, comparable_facts, indexable} for the default market (what crawlers see)."""
    mk = default_market(cat, older, newer)
    so, sn = pair_sides(cat, older, newer, mk)
    n = comparable_facts(diff(so, sn, mk))
    live = older.get("_status") != "cancelled" and newer.get("_status") != "cancelled"
    return {"market": mk, "comparable_facts": n, "indexable": bool(live and n >= MIN_COMPARABLE_FACTS)}


def pair_updated(cat, older, newer):
    vals = [older.get("updated_at"), newer.get("updated_at")] + \
           [v.get("catalog_updated_at") for g in (older, newer) for v in cat.variants_by_gen[g["id"]]]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def model_changes(cat, m) -> List[dict]:
    """The model tree's `changes` list, newest pair first."""
    out = []
    for older, newer in reversed(adjacent_pairs(cat.gens_by_model[m["id"]])):
        q = pair_quality(cat, older, newer)
        out.append({"path": pair_path(cat, m, older, newer),
                    "older": {"slug": older["slug"], "name": older["name"]},
                    "newer": {"slug": newer["slug"], "name": newer["name"]},
                    "indexable": q["indexable"]})
    return out


def _sources(*lists):
    seen, out = set(), []
    for lst in lists:
        for s in lst or []:
            k = (s.get("url"), s.get("name"))
            if k in seen:
                continue
            seen.add(k)
            out.append(s)
    return out


def changes_page(cat, m, older, newer, market: Optional[str] = None) -> dict:
    """Full response of GET /catalog/changes/... ; `market` must be one of the pair's markets or None."""
    make = cat.makes[m["make_id"]]
    model_name = display_name(make.get("catalog_name"), m["name"])
    quality = pair_quality(cat, older, newer)
    mk = market or quality["market"]
    so, sn = pair_sides(cat, older, newer, mk)
    rows = diff(so, sn, mk, mini=cat.variant_mini)
    labels = gen_labels(older, newer)
    for r in rows:
        r["qualifier"] = row_qualifier(r, mk)
        r["text"] = row_text(r, labels, mk)
    relation = "refresh" if newer.get("kind") == "refresh" else "new_generation"
    years_o, years_n = model_years(so), model_years(sn)

    matched, only_o, only_n = match_trims(so["live"], sn["live"])
    trims = {"matched": [], "only_older": [], "only_newer": []}
    for a, b, how in matched:
        ta = dict(so, scope=[a])
        tb = dict(sn, scope=[b])
        trows = [compare_number(k, ta, tb, mk, cat.variant_mini, trim=True) for k in TRIM_ROWS]
        trows = [r for r in trows if r is not None]
        for r in trows:
            r["qualifier"] = row_qualifier(r, mk)
            r["text"] = row_text(r, labels, mk, trim=True)
        trims["matched"].append({"older": dict(cat.variant_mini(a), status=a["_status"]),
                                 "newer": dict(cat.variant_mini(b), status=b["_status"]),
                                 "match": how, "rows": trows})
    trims["only_older"] = [dict(cat.variant_mini(v), status=v["_status"]) for v in only_o]
    trims["only_newer"] = [dict(cat.variant_mini(v), status=v["_status"]) for v in only_n]

    markets = pair_markets(cat, older, newer)
    notes = []
    if any(r["key"] == "entry_price" for r in rows):
        notes.append(PRICE_NOTE)
    if any((r.get(s) or {}).get("is_estimate") for r in rows for s in ("older", "newer")):
        notes.append(ESTIMATE_NOTE)
    path = pair_path(cat, m, older, newer)
    o_obj = dict(cat.gen_obj(older, with_variants=False), model_years=years_o, years_text=years_text(older))
    n_obj = dict(cat.gen_obj(newer, with_variants=False), model_years=years_n, years_text=years_text(newer))
    return {
        "path": path,
        "key": cat.key_of(path),
        "indexable": quality["indexable"],
        "quality": {"comparable_facts": comparable_facts(rows), "default_market": quality["market"],
                    "default_market_comparable_facts": quality["comparable_facts"],
                    "min_for_indexing": MIN_COMPARABLE_FACTS},
        "make": cat.make_mini(make),
        "model": {"slug": m["slug"], "name": m["name"], "path": cat.model_path(m),
                  "official_url": m["official_url"], "status": m["_status"], "years": cat.years(m)},
        "relation": relation,
        "older": o_obj,
        "newer": n_obj,
        "market": mk,
        "markets": markets,
        "summary": summary(model_name, older, newer, relation, rows, mk, labels),
        "rows": rows,
        "trims": trims,
        "faq": faq(model_name, rows, mk, labels, (years_o, years_n),
                   ([cat.variant_mini(v) for v in only_o], [cat.variant_mini(v) for v in only_n])),
        "notes": notes,
        "sources": _sources(older.get("sources"), newer.get("sources"),
                            *[v.get("sources") for v in so["live"] + sn["live"]]),
        "updated_at": _iso(pair_updated(cat, older, newer)),
    }
