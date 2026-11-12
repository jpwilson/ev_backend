"""Model-vs-model comparison pages (/compare/{a}-vs-{b}) and the pair index that decides which are indexable.

Pure functions over a whole-catalog snapshot (services/catalog_service.cached_catalog). Rows, wording and
comparability rules are those of the version-change pages (services/catalog_changes.py): two values are
compared only inside one group (price = market + currency + basis, range = market + unit + cycle, battery =
basis), nothing is converted, no overall verdict. Each model is represented by the trims of its default
(current) version that are on sale (services/catalog_lists.default_variants).

Pair index (FEATURES_BRIEF_2.md, "Comparisons"): sources in priority order pinned, relations (twins, successors),
same make with a different body style, rivals per market. A selected pair is indexable when it passes the
quality rule in its default market (pinned pairs are exempt) and is among the first MAX_INDEXED_PAIRS that pass.
Every other pair still answers, with indexable false. Selection is deterministic: every step is sorted.
"""
import math
from typing import Dict, List, Optional

import services.catalog_changes as C
import services.catalog_lists as L
from services.catalog_service import MARKETS, MARKET_PREFERENCE, _iso

MAX_INDEXED_PAIRS = 300
MIN_COMPARABLE_FACTS = C.MIN_COMPARABLE_FACTS          # 3
RIVAL_MARKETS = ("US", "EU", "UK", "CN")              # also the market preference for rivals
RIVAL_PRICE_RATIO = 1.3
RIVALS_PER_MODEL = 3
SAME_MAKE_PER_MODEL = 2
MORE_MAX = 6
LISTS_MAX = 6
ALTERNATIVES_MAX = 6
ALT_COMPARE_MAX = 6
ALT_LISTS_MAX = 5
SOURCES = ("pinned", "twin", "successor", "same_make", "rival")

# rows that get a highlight when comparable: which direction a buyer reads as the clear one
HIGHLIGHT = {"entry_price": "min", "longest_range": "max", "fastest_dc": "max",
             "quickest_0_60": "min", "quickest_0_100": "min"}
STATUS = {"increased": "b_higher", "decreased": "a_higher", "unchanged": "equal",
          "not_comparable": "not_comparable", "missing_older": "missing_a", "missing_newer": "missing_b",
          "changed": "different", "info": "info"}
SALE_WORDS = {"current": "on sale", "upcoming": "not on sale yet", "discontinued": "no longer on sale",
              "cancelled": "cancelled"}
SUMMARY_KEYS = ("entry_price", "longest_range", "fastest_dc", "quickest_0_60", "quickest_0_100")
SUMMARY_PHRASE = {"entry_price": "entry price", "longest_range": "longest range", "fastest_dc": "fastest DC charging peak",
                  "quickest_0_60": "quickest 0–60 mph", "quickest_0_100": "quickest 0–100 km/h"}


# ---------------------------------------------------------------- basics

def pair_slug(sa: str, sb: str) -> str:
    a, b = sorted((sa, sb))
    return "%s-vs-%s" % (a, b)


def pair_path(sa: str, sb: str) -> str:
    return "/compare/" + pair_slug(sa, sb)


def ordered(ma, mb):
    """(a, b) in canonical (alphabetical slug) order."""
    return (ma, mb) if ma["slug"] <= mb["slug"] else (mb, ma)


def by_slug(cat) -> Dict[str, dict]:
    memo = getattr(cat, "derived", None)
    if memo is not None and "by_slug" in memo:
        return memo["by_slug"]
    d = {m["slug"]: m for m in cat.models.values()}
    if memo is not None:
        memo["by_slug"] = d
    return d


def name_of(cat, m) -> str:
    return C.display_name(cat.makes[m["make_id"]]["catalog_name"], m["name"])


def selectable(cat, m) -> bool:
    """Eligible for a generated pair: on sale (current), not commercial, brand not defunct, default
    version not cancelled."""
    return m["_status"] == "current" and L.base_eligible(cat, m)


def side_of(cat, m, market):
    gen = cat.gens[m["_default_gen_id"]]
    return C.side(gen, L.default_variants(cat, m), cat.offerings, market)


def default_market(cat, ma, mb) -> Optional[str]:
    """US when both have US offerings, else the market with most comparable facts (ties by preference)."""
    return C.pick_market(cat.gens[ma["_default_gen_id"]], L.default_variants(cat, ma),
                         cat.gens[mb["_default_gen_id"]], L.default_variants(cat, mb), cat.offerings)


def pair_markets(cat, ma, mb) -> List[str]:
    """Markets where both have offerings (MARKETS order); when none is shared, where either has."""
    sa, sb = side_of(cat, ma, None), side_of(cat, mb, None)
    mk = (sa["markets"] & sb["markets"]) or (sa["markets"] | sb["markets"])
    return sorted(mk, key=lambda k: MARKETS.index(k) if k in MARKETS else 99)


def _rows(cat, ma, mb, market):
    return C.diff(side_of(cat, ma, market), side_of(cat, mb, market), market, mini=cat.variant_mini)


def _present(rows, key) -> bool:
    r = next((x for x in rows if x["key"] == key), None)
    return bool(r and r["older"] and r["newer"])


def quality(cat, ma, mb) -> dict:
    """Default market and the facts the indexing rule reads (for a, b in canonical order)."""
    if ma.get("_default_gen_id") is None or mb.get("_default_gen_id") is None:
        return {"default_market": None, "comparable_facts": 0, "has_price": False, "has_range": False}
    mk = default_market(cat, ma, mb)
    rows = _rows(cat, ma, mb, mk)
    return {"default_market": mk, "comparable_facts": C.comparable_facts(rows),
            "has_price": _present(rows, "entry_price"), "has_range": _present(rows, "longest_range")}


# ---------------------------------------------------------------- relations

def _relations(cat):
    memo = getattr(cat, "derived", None)
    if memo is not None and "relations" in memo:
        return memo["relations"]
    twins, succ = set(), {}
    for r in getattr(cat, "relation_rows", []):
        a, b = r["model_id"], r["related_model_id"]
        if a not in cat.models or b not in cat.models:
            continue
        if r["relation"] == "twin":
            twins.add(frozenset((a, b)))
        else:   # stored: model_id succeeds related_model_id
            succ[frozenset((a, b))] = a
    out = (twins, succ)
    if memo is not None:
        memo["relations"] = out
    return out


def relation(cat, ma, mb) -> Optional[dict]:
    """{"kind": "twin"|"successor"|"same_make", "newer": slug or None} for two models, or None."""
    twins, succ = _relations(cat)
    k = frozenset((ma["id"], mb["id"]))
    if k in twins:
        return {"kind": "twin", "newer": None}
    if k in succ:
        return {"kind": "successor", "newer": cat.models[succ[k]]["slug"]}
    if ma["make_id"] == mb["make_id"]:
        return {"kind": "same_make", "newer": None}
    return None


# ---------------------------------------------------------------- pair index

def _closeness(pa, pb) -> float:
    return abs(math.log(float(pa) / float(pb)))


def build_index(cat) -> dict:
    """Every selected pair in priority order with its quality and indexable flag (memoised on the
    cached catalog): {"pairs": [...], "by_key": {}, "by_model": {model_id: [indexable pairs]}}."""
    memo = getattr(cat, "derived", None)
    if memo is not None and "pair_index" in memo:
        return memo["pair_index"]
    from routers.seo import COMPARE_PAIRS   # the single pinned list
    slugs = by_slug(cat)
    selected: Dict[str, dict] = {}

    def add(ma, mb, source, market=None, closeness=None):
        if ma["id"] == mb["id"]:
            return
        a, b = ordered(ma, mb)
        k = pair_slug(a["slug"], b["slug"])
        if k not in selected:
            selected[k] = {"key": k, "path": "/compare/" + k, "a": a, "b": b, "source": source,
                           "selected_market": market, "closeness": closeness}

    # 1. pinned
    for p in COMPARE_PAIRS:
        sa, _, sb = p.partition("-vs-")
        if sa in slugs and sb in slugs:
            add(slugs[sa], slugs[sb], "pinned")
    # 2. relations: twins (both on sale), then successors (the successor on sale; the predecessor may be
    # discontinued but not commercial, defunct-brand or cancelled)
    twins, succ = _relations(cat)
    tw = []
    for k in twins:
        a, b = ordered(*[cat.models[i] for i in k])
        if selectable(cat, a) and selectable(cat, b):
            tw.append((pair_slug(a["slug"], b["slug"]), a, b))
    for _, a, b in sorted(tw, key=lambda t: t[0]):
        add(a, b, "twin")
    sc = []
    for k, newer_id in succ.items():
        older_id = next(i for i in k if i != newer_id)
        newer, older = cat.models[newer_id], cat.models[older_id]
        if selectable(cat, newer) and L.base_eligible(cat, older) and older["_status"] in ("current", "discontinued"):
            a, b = ordered(newer, older)
            sc.append((pair_slug(a["slug"], b["slug"]), a, b))
    for _, a, b in sorted(sc, key=lambda t: t[0]):
        add(a, b, "successor")

    # per-market facts of every model on sale there (prices in the market currency, main-cycle range)
    facts = {}
    pool = sorted([m for m in cat.models.values() if selectable(cat, m)], key=lambda m: m["slug"])
    for mk in RIVAL_MARKETS:
        for m in pool:
            if L.on_sale(cat, m, mk):
                f = L.market_facts(cat, m, mk)
                if f["price"]:
                    facts[(m["id"], mk)] = f

    # 3. same make, different body style: at most SAME_MAKE_PER_MODEL per model, nearest entry price first
    cands = []
    by_make: Dict[int, list] = {}
    for m in pool:
        by_make.setdefault(m["make_id"], []).append(m)
    for ms in by_make.values():
        for i, x in enumerate(ms):
            for y in ms[i + 1:]:
                if not x["body_style"] or not y["body_style"] or x["body_style"] == y["body_style"]:
                    continue
                for mk in RIVAL_MARKETS:
                    fx, fy = facts.get((x["id"], mk)), facts.get((y["id"], mk))
                    if fx and fy:
                        a, b = ordered(x, y)
                        cands.append((_closeness(fx["price"]["value"], fy["price"]["value"]),
                                      pair_slug(a["slug"], b["slug"]), a, b, mk))
                        break
    used: Dict[int, int] = {}
    for cl, _, a, b, mk in sorted(cands, key=lambda t: (t[0], t[1])):
        if used.get(a["id"], 0) < SAME_MAKE_PER_MODEL and used.get(b["id"], 0) < SAME_MAKE_PER_MODEL:
            used[a["id"]] = used.get(a["id"], 0) + 1
            used[b["id"]] = used.get(b["id"], 0) + 1
            add(a, b, "same_make", mk, round(cl, 4))

    # 4. rivals per market: same body style, different make, prices within RIVAL_PRICE_RATIO, both with a
    # main-cycle range; each model's RIVALS_PER_MODEL nearest by price
    rivals = []
    for mi, mk in enumerate(RIVAL_MARKETS):
        here = [m for m in pool if (m["id"], mk) in facts and facts[(m["id"], mk)]["range"]]
        for m in here:
            pm = facts[(m["id"], mk)]["price"]["value"]
            near = []
            for o in here:
                if o["make_id"] == m["make_id"] or o["body_style"] != m["body_style"] or not m["body_style"]:
                    continue
                po = facts[(o["id"], mk)]["price"]["value"]
                if max(pm, po) / float(min(pm, po)) <= RIVAL_PRICE_RATIO:
                    near.append((_closeness(pm, po), o["slug"], o))
            for cl, _, o in sorted(near, key=lambda t: (t[0], t[1]))[:RIVALS_PER_MODEL]:
                a, b = ordered(m, o)
                rivals.append((mi, cl, pair_slug(a["slug"], b["slug"]), a, b, mk))
    for mi, cl, _, a, b, mk in sorted(rivals, key=lambda t: (t[0], t[1], t[2])):
        add(a, b, "rival", mk, round(cl, 4))

    # quality + cap, in priority order
    pairs = list(selected.values())
    indexed = 0
    by_model: Dict[int, list] = {}
    for p in pairs:
        a, b = p["a"], p["b"]
        q = quality(cat, a, b)
        p["quality"] = q
        if p["source"] == "pinned":
            ok = a["_status"] != "cancelled" and b["_status"] != "cancelled"
            why = "pinned pair" if ok else "a pinned model is cancelled"
        else:
            ok, why = _passes(q)
        if ok and indexed < MAX_INDEXED_PAIRS:
            indexed += 1
            p["indexable"] = True
            p["reason"] = why
            by_model.setdefault(a["id"], []).append(p)
            by_model.setdefault(b["id"], []).append(p)
        else:
            p["indexable"] = False
            p["reason"] = ("beyond the cap of %d indexed pairs" % MAX_INDEXED_PAIRS) if ok else why
    out = {"pairs": pairs, "by_key": {p["key"]: p for p in pairs}, "by_model": by_model, "indexed": indexed}
    if memo is not None:
        memo["pair_index"] = out
    return out


def _passes(q):
    mk = q["default_market"]
    where = C.MARKET_SHORT.get(mk, mk) if mk else "any market"
    if not mk:
        return False, "no offerings on file for either model"
    if q["comparable_facts"] < MIN_COMPARABLE_FACTS:
        return False, "%d comparable figure%s in the %s data; at least %d are needed" % (
            q["comparable_facts"], "" if q["comparable_facts"] == 1 else "s", where, MIN_COMPARABLE_FACTS)
    if not q["has_price"]:
        return False, "no %s price on file for one of the two" % where
    if not q["has_range"]:
        return False, "no %s range on file for one of the two" % where
    return True, "%d comparable figures in the %s data" % (q["comparable_facts"], where)


def pair_entry(cat, p) -> dict:
    """One item of GET /catalog/compare-pairs."""
    def mini(m):
        return {"slug": m["slug"], "name": name_of(cat, m), "path": cat.model_path(m),
                "make": {"slug": cat.makes[m["make_id"]]["slug"], "name": cat.makes[m["make_id"]]["catalog_name"]}}
    q = p["quality"]
    return {"path": p["path"], "key": p["key"], "name": "%s vs %s" % (name_of(cat, p["a"]), name_of(cat, p["b"])),
            "a": mini(p["a"]), "b": mini(p["b"]), "source": p["source"], "market": q["default_market"],
            "selected_market": p["selected_market"], "comparable_facts": q["comparable_facts"],
            "indexable": p["indexable"], "reason": p["reason"]}


def pairs_response(cat, model_slug=None, indexable=None) -> dict:
    idx = build_index(cat)
    pairs = idx["pairs"]
    if model_slug:
        pairs = [p for p in pairs if model_slug in (p["a"]["slug"], p["b"]["slug"])]
    if indexable is not None:
        pairs = [p for p in pairs if p["indexable"] == indexable]
    stats = {s: {"selected": 0, "indexable": 0} for s in SOURCES}
    for p in idx["pairs"]:
        stats[p["source"]]["selected"] += 1
        stats[p["source"]]["indexable"] += int(p["indexable"])
    return {"count": len(pairs), "cap": MAX_INDEXED_PAIRS, "indexed": idx["indexed"], "by_source": stats,
            "pairs": [pair_entry(cat, p) for p in pairs]}


def indexable_pairs(cat) -> List[dict]:
    return [p for p in build_index(cat)["pairs"] if p["indexable"]]


def pair_updated(cat, ma, mb):
    vals = []
    for m in (ma, mb):
        gen = cat.gens.get(m["_default_gen_id"])
        vals.append(m.get("updated_at"))
        if gen:
            vals.append(gen.get("updated_at"))
            vals += [v.get("catalog_updated_at") for v in cat.variants_by_gen[gen["id"]]]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


# ---------------------------------------------------------------- text

def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" or word.startswith("SUV") else "a"


def _body(m) -> str:
    b = m.get("body_style")
    return L.BODY_SINGULAR.get(b, b) if b else "electric car"


def _sale(cat, m, mk) -> Optional[str]:
    return L.market_status(cat, m, mk) if mk else None


def row_text(row, names, mk) -> str:
    """Sentence for one row (row still in catalog_changes form: older = a, newer = b)."""
    A, B = names
    o, n, st = row["older"], row["newer"], row["change"]["status"]
    head = C.row_label(row, mk)

    def val(s):
        return C.fmt_value(row, s) + C._provenance(row, s)
    if st == "missing_older":
        return "%s: %s for the %s. Not on file for the %s." % (head, val(n), B, A)
    if st == "missing_newer":
        return "%s: %s for the %s. Not on file for the %s." % (head, val(o), A, B)
    if st == "not_comparable":
        return "%s: %s for the %s; %s for the %s. Not compared: %s." % (
            head, val(o), A, val(n), B, row["change"]["reason"])
    if row["kind"] in ("set", "span", "count"):
        if st == "unchanged":
            return "%s: %s for both." % (head, C.fmt_value(row, o))
        return "%s: %s for the %s; %s for the %s." % (head, C.fmt_value(row, o), A, C.fmt_value(row, n), B)
    if st == "unchanged":
        txt = "%s: %s for both the %s%s and the %s%s." % (
            head, C.fmt_value(row, o), A, C._provenance(row, o), B, C._provenance(row, n))
    else:
        txt = "%s: %s for the %s vs %s for the %s, %s for the %s." % (
            head, val(o), A, val(n), B, C.delta_text(row), B)
    if row["change"].get("basis_unknown"):
        txt += " " + C.BATTERY_UNKNOWN
    return txt


def to_row(row, names, mk) -> dict:
    """catalog_changes row -> compare row (a/b, compare{status...}, highlight, text)."""
    ch = row["change"]
    comp = {"status": STATUS.get(ch["status"], ch["status"]), "delta": ch["delta"], "unit": ch["unit"],
            "reason": ch["reason"]}
    if ch.get("basis_unknown"):
        comp["basis_unknown"] = True
    if "added" in ch:
        comp["only_b"], comp["only_a"] = ch["added"], ch["removed"]
    hl = None
    if row["key"] in HIGHLIGHT and C.is_comparable(row) and ch["status"] != "unchanged":
        b_larger = ch["delta"] > 0
        hl = "b" if b_larger == (HIGHLIGHT[row["key"]] == "max") else "a"
    label = "Trims on file (all markets)" if row["key"] == "trims" else row["label"]
    return {"key": row["key"], "label": label, "kind": row["kind"], "qualifier": C.row_qualifier(row, mk),
            "a": row["older"], "b": row["newer"], "compare": comp, "highlight": hl,
            "text": row_text(dict(row, label=label), names, mk)}


def _sale_sentence(cat, a, b, names, mk) -> Optional[str]:
    if not mk:
        return None
    A, B = names
    where = C.MARKET_IN.get(mk, mk)
    sa, sb = _sale(cat, a, mk), _sale(cat, b, mk)
    if sa == "current" and sb == "current":
        return "Both are on sale in %s." % where
    wa = SALE_WORDS.get(sa, "not listed in our data")
    wb = SALE_WORDS.get(sb, "not listed in our data")
    return "In %s, the %s is %s and the %s is %s." % (where, A, wa, B, wb)


def summary(cat, a, b, rel, rows, mk, names) -> List[str]:
    A, B = names
    out = []
    make_a, make_b = cat.makes[a["make_id"]], cat.makes[b["make_id"]]
    if rel and rel["kind"] == "twin":
        if a["make_id"] != b["make_id"]:
            out.append("The %s and the %s are twins: closely related models sold under different brands." % (A, B))
        else:
            out.append("The %s and the %s are twins: closely related %s models." % (A, B, make_a["catalog_name"]))
    elif rel and rel["kind"] == "successor":
        newer, older = (a, b) if rel["newer"] == a["slug"] else (b, a)
        N, O = (A, B) if newer is a else (B, A)

        def yrs(m):
            y = cat.years(m)
            if not y["start"]:
                return ""
            if y["end"]:
                return " (%s)" % (str(y["start"]) if y["start"] == y["end"] else "%d–%d" % (y["start"], y["end"]))
            return " (%d–present)" % y["start"] if m["_status"] == "current" else " (from %d)" % y["start"]
        verb = ("is the upcoming successor to" if newer["_status"] == "upcoming" else
                "is the successor to" if older["_status"] == "current" else "replaced")
        out.append("The %s%s %s the %s%s." % (N, yrs(newer), verb, O, yrs(older)))
    elif a["make_id"] == b["make_id"]:
        ba, bb = _body(a), _body(b)
        if ba == bb:
            out.append("Both are %s %s." % (make_a["catalog_name"], L.BODY_PLURAL.get(a["body_style"], ba + "s")))
        else:
            out.append("Both are %s models: the %s is %s %s and the %s is %s %s." % (
                make_a["catalog_name"], A, _article(ba), ba, B, _article(bb), bb))
    else:
        ba, bb = _body(a), _body(b)
        if ba == bb and a["body_style"]:
            out.append("The %s and the %s are both %s." % (A, B, L.BODY_PLURAL.get(a["body_style"], ba + "s")))
        else:
            out.append("The %s is %s %s and the %s is %s %s." % (A, _article(ba), ba, B, _article(bb), bb))
    s = _sale_sentence(cat, a, b, names, mk)
    if s:
        out.append(s)
    by = {r["key"]: r for r in rows}
    parts = []
    for key in SUMMARY_KEYS:
        r = by.get(key)
        if not r or not C.is_comparable(r) or len(parts) == 3:
            continue
        if key == "quickest_0_100" and "quickest_0_60" in [p[0] for p in parts]:
            continue
        o, n = r["older"], r["newer"]
        phrase = SUMMARY_PHRASE[key]
        if key == "longest_range":
            phrase = "longest %s range" % o["cycle"]
        tail = ""
        if key == "entry_price":
            tail = " (%s)" % C.PRICE_BASIS_TEXT.get(o["basis"], o["basis"])
        parts.append((key, "%s %s vs %s%s" % (phrase, C.fmt_value(r, o), C.fmt_value(r, n), tail)))
    if parts:
        out.append("Figures on file for %s, %s vs %s: %s." % (C.MARKET_IN.get(mk, mk), A, B,
                                                             "; ".join(p[1] for p in parts)))
    mks = C.MARKET_SHORT.get(mk, mk) if mk else None
    for key, noun in (("entry_price", "price"), ("longest_range", "range")):
        r = by.get(key)
        st = r["change"]["status"] if r else None
        if st in C.COMPARED:
            continue
        if not mk:
            out.append("No %s is on file for either model." % noun)
        elif r is None:
            out.append("No %s %s is on file for either model." % (mks, noun))
        elif st == "missing_older":
            out.append("No %s %s is on file for the %s." % (mks, noun, A))
        elif st == "missing_newer":
            out.append("No %s %s is on file for the %s." % (mks, noun, B))
        elif st == "not_comparable":
            out.append("%s %ss are on file for both, but %s, so they are not compared." % (
                mks, noun, r["change"]["reason"]))
    return out


def faq(cat, a, b, rows, mk, names) -> List[dict]:
    A, B = names
    by = {r["key"]: r for r in rows}
    where = " in %s" % C.MARKET_IN.get(mk, mk) if mk else ""
    out = []

    def pick(r, lower_wins):
        """(winner name, loser name, winner side, loser side) or None when equal."""
        o, n = r["older"], r["newer"]
        if r["change"]["status"] == "unchanged":
            return None
        b_lower = r["change"]["status"] == "decreased"     # delta = b - a
        b_wins = b_lower == lower_wins
        return (B, A, n, o) if b_wins else (A, B, o, n)

    def v(r, s):
        return C.fmt_value(r, s) + C._provenance(r, s)

    r = by.get("entry_price")
    if r and C.is_comparable(r):
        basis = C.PRICE_BASIS_TEXT.get(r["older"]["basis"], r["older"]["basis"])
        extra = " Destination charges are extra." if r["older"]["basis"] == "msrp_excl_destination" else ""
        w = pick(r, True)
        if w:
            ans = "The %s has the lower entry price on file%s: %s vs %s for the %s, both %s. %s%s" % (
                w[0], where, v(r, w[2]), v(r, w[3]), w[1], basis, C.PRICE_NOTE, extra)
        else:
            ans = "Both have the same entry price on file%s: %s (%s). %s%s" % (
                where, C.fmt_value(r, r["older"]), basis, C.PRICE_NOTE, extra)
        out.append({"q": "Which is cheaper, the %s or the %s?" % (A, B), "a": ans})
    r = by.get("longest_range")
    if r and C.is_comparable(r):
        cyc = r["older"]["cycle"]
        w = pick(r, False)
        note = L.RANGE_NOTE % cyc
        if w:
            ans = "The %s has the longer %s range on file%s: %s vs %s for the %s. %s" % (
                w[0], cyc, where, v(r, w[2]), v(r, w[3]), w[1], note)
        else:
            ans = "Both have the same longest %s range on file%s: %s. %s" % (cyc, where, C.fmt_value(r, r["older"]), note)
        out.append({"q": "Which has more range, the %s or the %s?" % (A, B), "a": ans})
    r = by.get("fastest_dc")
    if r and C.is_comparable(r):
        w = pick(r, False)
        if w:
            ans = "The %s has the higher published DC charging peak: %s vs %s for the %s. %s" % (
                w[0], v(r, w[2]), v(r, w[3]), w[1], L.DC_NOTE)
        else:
            ans = "Both have the same published DC charging peak: %s. %s" % (C.fmt_value(r, r["older"]), L.DC_NOTE)
        out.append({"q": "Which charges faster, the %s or the %s?" % (A, B), "a": ans})
    for key, label in (("quickest_0_60", "0–60 mph"), ("quickest_0_100", "0–100 km/h")):
        r = by.get(key)
        if r and C.is_comparable(r):
            w = pick(r, True)
            if w:
                ans = "The %s has the quicker published %s time: %s vs %s for the %s." % (
                    w[0], label, v(r, w[2]), v(r, w[3]), w[1])
            else:
                ans = "Both have the same quickest published %s time: %s." % (label, C.fmt_value(r, r["older"]))
            out.append({"q": "Which is quicker from %s, the %s or the %s?" % (
                label.replace("–", " to "), A, B), "a": ans})
            break
    ma, mb = L.current_markets(cat, a), L.current_markets(cat, b)
    if ma or mb:
        def lst(ms):
            return C._and([C.MARKET_IN.get(x, x) for x in ms]) if ms else None
        if ma == mb:
            ans = "In our data, both are on sale in %s." % lst(ma)
        else:
            bits = []
            for nm, m, ms in ((A, a, ma), (B, b, mb)):
                gone = {"discontinued": "no longer", "upcoming": "not yet"}.get(m["_status"], "not")
                bits.append("the %s is on sale in %s" % (nm, lst(ms)) if ms else
                            "the %s is %s on sale in any market we cover" % (nm, gone))
            ans = "In our data, %s." % "; ".join(bits)
        out.append({"q": "Where are the %s and the %s on sale?" % (A, B), "a": ans})
    return out


# ---------------------------------------------------------------- page

def side_obj(cat, m, mk) -> dict:
    make = cat.makes[m["make_id"]]
    gen = cat.gens.get(m["_default_gen_id"])
    return {
        "name": name_of(cat, m),
        "make": cat.make_mini(make),
        "model": {"slug": m["slug"], "name": m["name"], "path": cat.model_path(m), "status": m["_status"],
                  "body_style": m["body_style"], "years": cat.years(m), "official_url": m["official_url"]},
        "generation": {"slug": gen["slug"], "name": gen["name"], "path": cat.gen_path(gen),
                       "years": C.years_text(gen), "status": gen["_status"],
                       "image": cat.primary_image(gen["id"]), "description": gen["description"]} if gen else None,
        "market_status": _sale(cat, m, mk),
        "on_sale_in": L.current_markets(cat, m),
    }


def _more(cat, p, m) -> List[dict]:
    out = []
    for q in build_index(cat)["by_model"].get(m["id"], []):
        if q["key"] == p["key"]:
            continue
        other = q["b"] if q["a"]["id"] == m["id"] else q["a"]
        out.append({"path": q["path"], "key": q["key"], "name": "%s vs %s" % (name_of(cat, q["a"]), name_of(cat, q["b"])),
                    "other": {"slug": other["slug"], "name": name_of(cat, other), "path": cat.model_path(other)}})
        if len(out) == MORE_MAX:
            break
    return out


def _lists(cat, a, b) -> List[dict]:
    ra = {x["key"]: x for x in L.ranks_of(cat, a["slug"])}
    rb = {x["key"]: x for x in L.ranks_of(cat, b["slug"])}
    out = []
    for cfg in L.LISTS:
        k = cfg["key"]
        if k in ra or k in rb:
            x = ra.get(k) or rb.get(k)
            out.append({"key": k, "title": x["title"], "path": x["path"], "market": x["market"], "count": x["count"],
                        "a_rank": (ra.get(k) or {}).get("rank"), "b_rank": (rb.get(k) or {}).get("rank")})
    return out[:LISTS_MAX]


def page(cat, ma, mb, market: Optional[str] = None) -> dict:
    """Full body of GET /catalog/compare/{a}/{b}; `market` must be one of pair_markets or None."""
    a, b = ordered(ma, mb)
    idx = build_index(cat)
    k = pair_slug(a["slug"], b["slug"])
    p = idx["by_key"].get(k)
    if p:
        q, indexable, source, reason = p["quality"], p["indexable"], p["source"], p["reason"]
    else:
        q, indexable, source, reason = quality(cat, a, b), False, None, "not a selected pair"
    mk = market or q["default_market"]
    names = (name_of(cat, a), name_of(cat, b))
    if names[0] == names[1]:
        names = ("%s (%s)" % (names[0], a["slug"]), "%s (%s)" % (names[1], b["slug"]))
    sa, sb = side_of(cat, a, mk), side_of(cat, b, mk)
    raw = C.diff(sa, sb, mk, mini=cat.variant_mini)
    # model years are only worth a row when both sides have them (EU/CN offerings carry none)
    raw = [r for r in raw if r["key"] != "model_years" or (r["older"] and r["newer"])]
    rows = [to_row(r, names, mk) for r in raw]
    rel = relation(cat, a, b)
    notes = []
    if any(r["key"] == "entry_price" for r in raw):
        notes.append(C.PRICE_NOTE)
        if any((r.get(s) or {}).get("basis") == "msrp_excl_destination" for r in raw if r["key"] == "entry_price"
               for s in ("older", "newer")):
            notes.append(L.PRICE_EXCL_NOTE)
    if any(r["key"] == "fastest_dc" for r in raw):
        notes.append(L.DC_NOTE)
    if any((r.get(s) or {}).get("is_estimate") for r in raw for s in ("older", "newer")):
        notes.append(C.ESTIMATE_NOTE)
    if mk:
        notes.append("Each model is represented by the trims of its current version on sale; prices, ranges and "
                     "connectors are those on file for %s." % C.MARKET_IN.get(mk, mk))
    path = "/compare/" + k
    return {
        "path": path,
        "key": k,
        "indexable": indexable,
        "quality": {"default_market": q["default_market"], "comparable_facts": q["comparable_facts"],
                    "has_price": q["has_price"], "has_range": q["has_range"], "source": source, "reason": reason,
                    "min_for_indexing": MIN_COMPARABLE_FACTS, "comparable_facts_shown": C.comparable_facts(raw)},
        "relation": rel,
        "a": side_obj(cat, a, mk),
        "b": side_obj(cat, b, mk),
        "market": mk,
        "markets": pair_markets(cat, a, b),
        "summary": summary(cat, a, b, rel, raw, mk, names),
        "rows": rows,
        "faq": faq(cat, a, b, raw, mk, names),
        "more": {"a": _more(cat, p, a), "b": _more(cat, p, b)} if indexable else {"a": [], "b": []},
        "lists": _lists(cat, a, b),
        "notes": notes,
        "sources": C._sources(a.get("sources"), b.get("sources"),
                              *[cat.gens[m["_default_gen_id"]].get("sources") for m in (a, b) if m["_default_gen_id"]],
                              *[v.get("sources") for v in sa["scope"] + sb["scope"]]),
        "updated_at": _iso(pair_updated(cat, a, b)),
    }


# ---------------------------------------------------------------- model-page links

def alternatives(cat, m, market: Optional[str] = None) -> dict:
    """Body of GET /catalog/models/{make}/{model}/alternatives."""
    order = lambda k: MARKET_PREFERENCE.index(k) if k in MARKET_PREFERENCE else 99  # noqa: E731
    markets = sorted(L.current_markets(cat, m), key=order)
    if not markets and m.get("_default_gen_id"):
        markets = sorted(side_of(cat, m, None)["markets"], key=order)
    mk = market
    if mk is None and markets:
        # the first market (in preference order) where the model has a price or a main-cycle range on file
        mk = next((k for k in markets if any(L.market_facts(cat, m, k, allow_estimates=True)[f]
                                             for f in ("price", "range"))), markets[0])
    name = name_of(cat, m)
    alts, rule = [], None
    if mk and m.get("_default_gen_id"):
        mine = L.market_facts(cat, m, mk, allow_estimates=m["_status"] == "upcoming")
        by = "price" if mine["price"] else "range" if mine["range"] else None
        noun = L.BODY_PLURAL.get(m["body_style"], "electric cars") if m["body_style"] else "electric cars"
        where = C.MARKET_IN.get(mk, mk)
        if by:
            mv = mine[by]["value"]
            lo, hi = int(math.ceil(mv / RIVAL_PRICE_RATIO)), int(math.floor(mv * RIVAL_PRICE_RATIO))
            if by == "price":
                cur = mine["price"]["currency"]
                rule = ("Other %s on sale in %s with a lowest published price from %s to %s, closest in price "
                        "first. The %s starts at %s on file (%s)." % (
                            noun, where, C._money(lo, cur), C._money(hi, cur), name, L.price_text(mine["price"]),
                            L.basis_text(mine["price"])))
            else:
                r, u = mine["range"], mine["range"]["unit"]
                rule = ("No %s price is on file for the %s, so similar cars are matched by range: other %s on sale "
                        "in %s with a longest %s range from %s to %s %s, closest first. The %s's longest is %s %s." % (
                            C.MARKET_SHORT.get(mk, mk), name, noun, where, r["cycle"], C._fmt_num(lo), C._fmt_num(hi),
                            u, name, C._fmt_num(mv), u))
            cands = []
            for o in cat.models.values():
                if o["id"] == m["id"] or o["body_style"] != m["body_style"] or not selectable(cat, o) \
                        or not L.on_sale(cat, o, mk):
                    continue
                f = L.market_facts(cat, o, mk)
                if not f[by]:
                    continue
                ov = f[by]["value"]
                if max(mv, ov) / float(min(mv, ov)) <= RIVAL_PRICE_RATIO:
                    cands.append((_closeness(mv, ov), o["slug"], o, f))
            for _, _, o, f in sorted(cands, key=lambda t: (t[0], t[1]))[:ALTERNATIVES_MAX]:
                p = build_index(cat)["by_key"].get(pair_slug(m["slug"], o["slug"]))
                rel = relation(cat, m, o)
                kind = None
                if rel:
                    kind = rel["kind"]
                    if kind == "successor":
                        kind = "successor" if rel["newer"] == o["slug"] else "predecessor"
                alts.append({"card": cat.model_card(o, mk), "price": f["price"], "range": f["range"],
                             "compare_path": p["path"] if p and p["indexable"] else None, "relation": kind})
        else:
            rule = "No price or %s range is on file for the %s in %s, so no similar cars are suggested." % (
                L.PRIMARY_RANGE_CYCLE.get(mk, "main-cycle"), name, where)
    compare = []
    for p in build_index(cat)["by_model"].get(m["id"], [])[:ALT_COMPARE_MAX]:
        other = p["b"] if p["a"]["id"] == m["id"] else p["a"]
        compare.append({"path": p["path"], "key": p["key"], "name": "%s vs %s" % (name_of(cat, p["a"]), name_of(cat, p["b"])),
                        "source": p["source"],
                        "other": {"slug": other["slug"], "name": name_of(cat, other), "path": cat.model_path(other)}})
    lists = [{k: x[k] for k in ("key", "title", "path", "rank", "count", "market")}
             for x in L.ranks_of(cat, m["slug"])[:ALT_LISTS_MAX]]
    return {"model": {"slug": m["slug"], "name": name, "path": cat.model_path(m)}, "market": mk, "markets": markets,
            "rule": rule, "alternatives": alts, "compare": compare, "lists": lists}
