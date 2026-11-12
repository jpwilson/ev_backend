"""Read side of the catalog: loads the hierarchy, computes effective statuses once,
and serialises it for /catalog/*.

All reads use the Core tables in services/catalog_tables.py (never the legacy ORM).
A Catalog is an in-memory snapshot of one request's slice of the data: everything
for list endpoints, one make or one model for detail endpoints.
"""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import and_, func, select, text

import services.catalog_status as S
import services.catalog_tables as T

MARKETS = ("US", "CA", "EU", "UK", "CN", "JP", "KR", "IN", "AU")
MARKET_PREFERENCE = ("US", "EU", "UK", "CN", "CA", "JP", "KR", "AU", "IN")
LIFECYCLE = S.LIFECYCLE
PRIMARY_RANGE_CYCLE = {"US": "EPA", "CA": "EPA", "EU": "WLTP", "UK": "WLTP", "CN": "CLTC",
                       "JP": "WLTC", "KR": "KR", "IN": "MIDC", "AU": "WLTP"}


def tables_ready(conn) -> bool:
    names = ", ".join("to_regclass('public.%s')" % t for t in T.REQUIRED_TABLES)
    row = conn.execute(text("SELECT %s" % names)).first()
    return all(v is not None for v in row)


def _num(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f.is_integer() else f
    return v


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _variant_order(v):
    """Seed order (researchers list variants base to top), then id."""
    return (v["variant_order"] if v["variant_order"] is not None else 999, v["id"])


def make_path(make) -> str:
    return "/make/%s" % make["slug"]


class Catalog:
    """Rows keyed by id, with effective statuses attached as '_status'."""

    def __init__(self, conn, make_slug: Optional[str] = None, model_key: Optional[tuple] = None,
                 model_ids: Optional[Iterable[int]] = None):
        self.conn = conn
        # a partial slice (one model, or a set of models) cannot count a make's models
        self.partial = bool(model_key) or model_ids is not None
        mk = T.makes
        mq = select(mk).where(mk.c.slug.isnot(None))
        if make_slug or model_key:
            mq = mq.where(mk.c.slug == (make_slug or model_key[0]))
        self.makes = {r["id"]: dict(r) for r in conn.execute(mq).mappings()}

        md = T.models
        q = select(md).where(md.c.url_slug.isnot(None), md.c.make_id.in_(list(self.makes) or [-1]))
        if model_key:
            q = q.where(md.c.url_slug == model_key[1])
        if model_ids is not None:
            q = q.where(md.c.id.in_(list(model_ids) or [-1]))
        self.models = {r["id"]: dict(r) for r in conn.execute(q).mappings()}
        mids = list(self.models) or [-1]

        g = T.generations
        self.gens = {r["id"]: dict(r) for r in conn.execute(select(g).where(g.c.model_id.in_(mids))).mappings()}
        gids = list(self.gens) or [-1]

        c = T.cars
        cols = [c.c.id, c.c.generation_id, c.c.variant_slug, c.c.variant_name, c.c.status,
                c.c.year_from, c.c.year_to, c.c.drivetrain, c.c.body_type, c.c.seats,
                c.c.battery_kwh, c.c.battery_basis, c.c.power_hp, c.c.torque_lbft,
                c.c.accel_0_60_s, c.c.accel_0_100_s, c.c.top_speed_mph, c.c.dc_kw,
                c.c.sources, c.c.catalog_updated_at, c.c.catalog_origin, c.c.variant_order]
        self.variants = {r["id"]: dict(r) for r in conn.execute(
            select(*cols).where(c.c.generation_id.in_(gids))).mappings()}
        vids = list(self.variants) or [-1]

        vm = T.variant_markets
        self.offerings = defaultdict(list)
        for r in conn.execute(select(vm).where(vm.c.car_id.in_(vids))).mappings():
            self.offerings[r["car_id"]].append(dict(r))

        im = T.images
        self.images = defaultdict(list)
        for r in conn.execute(select(im).where(im.c.model_id.in_(mids), im.c.verified.is_(True))
                              .order_by(im.c.generation_id, im.c.sort_order, im.c.id)).mappings():
            self.images[r["generation_id"]].append(dict(r))

        mm = T.model_markets
        self.markets = defaultdict(dict)
        for r in conn.execute(select(mm).where(mm.c.model_id.in_(mids))).mappings():
            self.markets[r["model_id"]][r["market"]] = dict(r)

        self.gens_by_model = defaultdict(list)
        for gen in self.gens.values():
            self.gens_by_model[gen["model_id"]].append(gen)
        self.variants_by_gen = defaultdict(list)
        for v in self.variants.values():
            self.variants_by_gen[v["generation_id"]].append(v)
        self._compute_status()

    # ---- status --------------------------------------------------------

    def _compute_status(self):
        self.warnings = []
        for m in self.models.values():
            make = self.makes[m["make_id"]]
            ms = make["catalog_status"]
            m["_status"] = S.model_status(m["status"], ms)
            for gen in self.gens_by_model[m["id"]]:
                gen["_status"] = S.generation_status(gen["status"], m["_status"], ms)
                w = S.consistency_warning(gen["status"], m["status"])
                if w:
                    self.warnings.append("%s/%s: %s" % (m["slug"], gen["slug"], w))
                for v in self.variants_by_gen[gen["id"]]:
                    v["_status"] = S.variant_status(v["status"], gen["status"], gen["_status"], ms)
            for code, mk in self.markets[m["id"]].items():
                mk["_status"] = S.market_status(mk["status"], m["_status"], ms)
            gens = self.gens_by_model[m["id"]]
            d = S.default_generation([dict(g, status=g["_status"]) for g in gens])
            m["_default_gen_id"] = d["id"] if d else None
        for make in self.makes.values():
            make["_models"] = [m for m in self.models.values() if m["make_id"] == make["id"]]
            make["_display"] = None if self.partial else S.make_display_status(
                make["catalog_status"], [m["_status"] for m in make["_models"]])

    # ---- paths ---------------------------------------------------------

    def model_path(self, m) -> str:
        return "/make/%s/%s" % (self.makes[m["make_id"]]["slug"], m["url_slug"])

    def gen_path(self, gen) -> str:
        return "%s/%s" % (self.model_path(self.models[gen["model_id"]]), gen["slug"])

    def variant_path(self, v) -> str:
        return "%s/%s" % (self.gen_path(self.gens[v["generation_id"]]), v["variant_slug"])

    @staticmethod
    def key_of(path: str) -> str:
        return path[len("/make/"):]

    # ---- serialisers ---------------------------------------------------

    def make_summary(self, make) -> dict:
        counts = Counter(m["_status"] for m in make.get("_models", []))
        return {
            "slug": make["slug"],
            "name": make["catalog_name"],
            "path": make_path(make),
            "status": make["catalog_status"],
            "brand_status": S.brand_status(make["catalog_status"]),
            "display_status": make.get("_display"),
            "status_date": make["status_date"],
            "status_details": make["catalog_status_details"],
            "country": make["catalog_country"],
            "founded": make["founded"],
            "logo_url": make["lrg_logo_img_url"],
            "model_counts": None if self.partial else {s: counts.get(s, 0) for s in LIFECYCLE},
        }

    def make_full(self, make) -> dict:
        d = self.make_summary(make)
        d.update({
            "headquarters": make["catalog_headquarters"],
            "parent_group": make["parent_group"],
            "website_url": make["catalog_website_url"],
            "description": make["catalog_description"],
            "sources": make["sources"] or [],
            "legacy_id": make["id"] if make["catalog_origin"] is None else None,
        })
        return d

    def make_mini(self, make) -> dict:
        return {"slug": make["slug"], "name": make["catalog_name"], "path": make_path(make),
                "status": make["catalog_status"], "brand_status": S.brand_status(make["catalog_status"]),
                "status_date": make["status_date"]}

    def image(self, im) -> dict:
        return {"url": im["file_url"], "source": im["source"], "page_url": im["page_url"],
                "credit": im["credit"], "license": im["license"], "view": im["view"],
                "alt": im["alt_text"], "is_primary": im["is_primary"],
                "width": im["width"], "height": im["height"]}

    def primary_image(self, gen_id) -> Optional[dict]:
        imgs = self.images.get(gen_id) or []
        for im in imgs:
            if im["is_primary"]:
                return self.image(im)
        return self.image(imgs[0]) if imgs else None

    @staticmethod
    def offering(o) -> dict:
        return {
            "market": o["market"], "model_year": o["model_year"],
            "price": _num(o["current_price"]), "launch_price": _num(o["launch_price"]),
            "currency": o["currency"], "price_basis": o["price_basis"],
            "range": _num(o["range_value"]), "range_unit": o["range_unit"], "range_cycle": o["range_cycle"],
            "connector": o["connector"], "is_estimate": o["is_estimate"],
        }

    def variant_mini(self, v) -> dict:
        return {"id": v["id"], "slug": v["variant_slug"], "name": v["variant_name"], "path": self.variant_path(v)}

    def variant_obj(self, v) -> dict:
        gen = self.gens[v["generation_id"]]
        m = self.models[gen["model_id"]]
        path = self.variant_path(v)
        offers = sorted(self.offerings.get(v["id"], []),
                        key=lambda o: (MARKETS.index(o["market"]) if o["market"] in MARKETS else 99,
                                       -(o["model_year"] or 9999)))
        return {
            "id": v["id"], "slug": v["variant_slug"], "key": self.key_of(path), "path": path,
            "name": v["variant_name"], "status": v["_status"], "own_status": v["status"],
            "year_from": v["year_from"], "year_to": v["year_to"], "drivetrain": v["drivetrain"],
            "body_type": v["body_type"] or m["body_style"], "seats": v["seats"],
            "battery_kwh": v["battery_kwh"], "battery_basis": v["battery_basis"],
            "power_hp": v["power_hp"], "torque_lbft": v["torque_lbft"],
            "accel_0_60_s": v["accel_0_60_s"], "accel_0_100_s": v["accel_0_100_s"],
            "top_speed_mph": v["top_speed_mph"], "dc_kw": v["dc_kw"],
            "offerings": [self.offering(o) for o in offers],
            "sources": v["sources"] or [],
            "updated_at": _iso(v["catalog_updated_at"]),
        }

    def gen_obj(self, gen, with_variants=True) -> dict:
        m = self.models[gen["model_id"]]
        path = self.gen_path(gen)
        d = {
            "id": gen["id"], "slug": gen["slug"], "key": self.key_of(path), "path": path,
            "name": gen["name"], "kind": gen["kind"], "ordinal": gen["ordinal"],
            "code_name": gen["code_name"], "platform": gen["platform"],
            "start_year": gen["start_year"], "end_year": gen["end_year"],
            "status": gen["_status"], "own_status": gen["status"],
            "description": gen["description"], "is_default": gen["id"] == m["_default_gen_id"],
            "images": [self.image(im) for im in self.images.get(gen["id"], [])],
            "sources": gen["sources"] or [],
            "updated_at": _iso(gen["updated_at"]),
        }
        if with_variants:
            vs = sorted(self.variants_by_gen[gen["id"]], key=_variant_order)
            d["variants"] = [self.variant_obj(v) for v in vs]
        return d

    def gens_newest_first(self, model_id) -> List[dict]:
        return sorted(self.gens_by_model[model_id], key=S.generation_sort_key, reverse=True)

    def years(self, m) -> dict:
        gens = [g for g in self.gens_by_model[m["id"]] if g["_status"] != "cancelled"] or self.gens_by_model[m["id"]]
        starts = [g["start_year"] for g in gens if g["start_year"]]
        ends = [g["end_year"] for g in gens]
        return {"start": min(starts) if starts else None,
                "end": None if (not ends or any(e is None for e in ends)) else max(ends)}

    def _card_market(self, m, market: Optional[str], variants) -> Optional[str]:
        if market:
            return market
        have = {o["market"] for v in variants for o in self.offerings.get(v["id"], [])}
        for code in MARKET_PREFERENCE:
            if code in have:
                return code
        return None

    def headline(self, m, market: Optional[str] = None) -> dict:
        """from-price, max range, quickest 0-60/0-100 over the default generation, each naming its variant."""
        gid = m["_default_gen_id"]
        variants = [v for v in self.variants_by_gen.get(gid, []) if v["_status"] != "cancelled"]
        mkt = self._card_market(m, market, variants)
        latest = {}
        for v in variants:
            offs = [o for o in self.offerings.get(v["id"], []) if o["market"] == mkt]
            if offs:
                latest[v["id"]] = offs
        price_cands, range_cands = [], []
        for vid, offs in latest.items():
            offs = sorted(offs, key=lambda o: o["model_year"] or 9999, reverse=True)
            p = next((o for o in offs if o["current_price"] is not None), None)
            r = next((o for o in offs if o["range_value"] is not None), None)
            if p:
                price_cands.append((vid, p))
            if r:
                range_cands.append((vid, r))
        out = {"market": mkt, "from_price": None, "max_range": None, "quickest_0_60": None, "quickest_0_100": None}
        if price_cands:
            cur = Counter(p["currency"] for _, p in price_cands).most_common(1)[0][0]
            vid, p = min(((v, p) for v, p in price_cands if p["currency"] == cur), key=lambda t: t[1]["current_price"])
            out["from_price"] = {"value": _num(p["current_price"]), "currency": p["currency"],
                                 "basis": p["price_basis"], "market": p["market"], "model_year": p["model_year"],
                                 "is_estimate": p["is_estimate"], "variant": self.variant_mini(self.variants[vid])}
        if range_cands:
            cycles = Counter(r["range_cycle"] for _, r in range_cands)
            pref = PRIMARY_RANGE_CYCLE.get(mkt)
            cyc = pref if pref in cycles else cycles.most_common(1)[0][0]
            vid, r = max(((v, r) for v, r in range_cands if r["range_cycle"] == cyc), key=lambda t: t[1]["range_value"])
            out["max_range"] = {"value": _num(r["range_value"]), "unit": r["range_unit"], "cycle": r["range_cycle"],
                                "market": r["market"], "model_year": r["model_year"], "is_estimate": r["is_estimate"],
                                "variant": self.variant_mini(self.variants[vid])}
        for field, key in (("accel_0_60_s", "quickest_0_60"), ("accel_0_100_s", "quickest_0_100")):
            cands = [v for v in variants if v[field] is not None]
            if cands:
                v = min(cands, key=lambda x: x[field])
                out[key] = {"value": v[field], "unit": "s", "variant": self.variant_mini(v)}
        return out

    def model_card(self, m, market: Optional[str] = None) -> dict:
        make = self.makes[m["make_id"]]
        path = self.model_path(m)
        gid = m["_default_gen_id"]
        gen = self.gens.get(gid)
        h = self.headline(m, market)
        card = {
            "slug": m["slug"], "key": self.key_of(path), "url_slug": m["url_slug"], "path": path,
            "name": m["name"], "make": self.make_mini(make),
            "status": m["_status"], "own_status": m["status"],
            "brand_status": S.brand_status(make["catalog_status"]),
            "body_style": m["body_style"], "is_commercial": m["is_commercial"],
            "aliases": list(m["aliases"] or []), "years": self.years(m),
            "markets": sorted(self.markets[m["id"]]),
            "default_generation": {"slug": gen["slug"], "name": gen["name"], "path": self.gen_path(gen)} if gen else None,
            "image": self.primary_image(gid) if gid else None,
            "headline_market": h["market"],
            "from_price": h["from_price"], "max_range": h["max_range"],
            "quickest_0_60": h["quickest_0_60"], "quickest_0_100": h["quickest_0_100"],
            "variant_count": len(self.variants_by_gen.get(gid, [])) if gid else 0,
        }
        if market:
            mk = self.markets[m["id"]].get(market)
            card["market_status"] = mk["_status"] if mk else None
        return card

    def relations(self, m) -> List[dict]:
        r = T.model_relations
        rows = self.conn.execute(select(r).where((r.c.model_id == m["id"]) | (r.c.related_model_id == m["id"]))).mappings().all()
        other_ids = {x["related_model_id"] if x["model_id"] == m["id"] else x["model_id"] for x in rows}
        if not other_ids:
            return []
        other = Catalog(self.conn, model_ids=other_ids)
        out = []
        for x in rows:
            mine = x["model_id"] == m["id"]
            oid = x["related_model_id"] if mine else x["model_id"]
            if oid not in other.models:
                continue
            if x["relation"] == "twin":
                rel = "twin"
            else:  # stored: model_id succeeds related_model_id
                rel = "predecessor" if mine else "successor"
            om = other.models[oid]
            out.append({"relation": rel, "model": {
                "slug": om["slug"], "name": om["name"], "path": other.model_path(om),
                "make": other.make_mini(other.makes[om["make_id"]]), "status": om["_status"]}})
        return out

    def changes(self, m) -> List[dict]:
        """Version-change pages of this model (adjacent generation pairs), newest first."""
        import services.catalog_changes as C  # imports this module
        return C.model_changes(self, m)

    def model_tree(self, m) -> dict:
        make = self.makes[m["make_id"]]
        path = self.model_path(m)
        gens = self.gens_newest_first(m["id"])
        default = self.gens.get(m["_default_gen_id"])
        updated = [m["updated_at"]] + [g["updated_at"] for g in gens] + \
                  [v["catalog_updated_at"] for g in gens for v in self.variants_by_gen[g["id"]]]
        return {
            "make": self.make_full(make),
            "model": {
                "slug": m["slug"], "key": self.key_of(path), "url_slug": m["url_slug"], "path": path,
                "name": m["name"], "aliases": list(m["aliases"] or []), "body_style": m["body_style"],
                "is_commercial": m["is_commercial"], "status": m["_status"], "own_status": m["status"],
                "brand_status": S.brand_status(make["catalog_status"]), "years": self.years(m),
                "description": m["description"], "official_url": m["official_url"],
                "markets": [{"market": code, "status": mk["_status"], "own_status": mk["status"],
                             "local_name": mk["local_name"], "launch": mk["launch_date"], "end": mk["end_date"]}
                            for code, mk in sorted(self.markets[m["id"]].items(),
                                                   key=lambda kv: MARKETS.index(kv[0]) if kv[0] in MARKETS else 99)],
                "sources": m["sources"] or [],
            },
            "headline": self.headline(m),
            "default_generation": default["slug"] if default else None,
            "generations": [self.gen_obj(g) for g in gens],
            "changes": self.changes(m),
            "relations": self.relations(m),
            "updated_at": _iso(max([u for u in updated if u is not None], default=None)),
        }


# ---------------------------------------------------------------- whole-catalog cache

# Row counts are part of the key so a delete (which moves no max(updated_at)) also invalidates.
_VERSION_SQL = text("""SELECT concat_ws('|', current_database(),
    (SELECT max(catalog_updated_at)::text || '/' || count(*) FROM makes),
    (SELECT max(updated_at)::text || '/' || count(*) FROM models),
    (SELECT max(updated_at)::text || '/' || count(*) FROM generations),
    (SELECT max(catalog_updated_at)::text || '/' || count(*) FROM cars WHERE generation_id IS NOT NULL),
    (SELECT max(updated_at)::text || '/' || count(*) FROM variant_markets),
    (SELECT max(updated_at)::text || '/' || count(*) FROM model_markets),
    (SELECT max(updated_at)::text || '/' || count(*) FROM images),
    (SELECT count(*)::text || '/' || coalesce(sum(hashtext(model_id || '-' || related_model_id || relation)), 0)
       FROM model_relations))""")
_CACHE: Dict[str, "Catalog"] = {}


def data_version(conn) -> str:
    """Cheap fingerprint of the catalog data (database name, newest change and row count per table)."""
    return conn.execute(_VERSION_SQL).scalar()


def cached_catalog(conn) -> "Catalog":
    """The whole catalog, loaded once per process per data version. Read-only: callers must not
    mutate it. Carries `relation_rows` (all model_relations) and `derived`, a memo for values
    computed from the whole catalog (compare pair index, lists), which dies with it."""
    version = data_version(conn)
    cat = _CACHE.get(version)
    if cat is None:
        cat = Catalog(conn)
        r = T.model_relations
        cat.relation_rows = [dict(x) for x in conn.execute(
            select(r.c.model_id, r.c.related_model_id, r.c.relation)).mappings()]
        cat.conn = None   # never reuse a request's connection
        cat.version = version
        cat.derived = {}
        _CACHE.clear()
        _CACHE[version] = cat
    return cat


# ---------------------------------------------------------------- queries

def meta(conn) -> dict:
    cat = Catalog(conn)
    q = text("""SELECT greatest(
        (SELECT max(catalog_updated_at) FROM makes),
        (SELECT max(updated_at) FROM models WHERE url_slug IS NOT NULL),
        (SELECT max(updated_at) FROM generations),
        (SELECT max(catalog_updated_at) FROM cars WHERE generation_id IS NOT NULL),
        (SELECT max(updated_at) FROM variant_markets),
        (SELECT max(updated_at) FROM images))""")
    as_of = conn.execute(q).scalar()
    return {
        "counts": {
            "makes": len(cat.makes), "models": len(cat.models), "generations": len(cat.gens),
            "variants": len(cat.variants), "offerings": sum(len(v) for v in cat.offerings.values()),
            "images": sum(len(v) for v in cat.images.values()),
        },
        "models_by_status": dict(Counter(m["_status"] for m in cat.models.values())),
        "makes_by_display_status": dict(Counter(mk["_display"] for mk in cat.makes.values())),
        "markets": sorted({code for mm in cat.markets.values() for code in mm}),
        "dataAsOf": as_of.date().isoformat() if as_of else None,
        "data_updated_at": _iso(as_of),
    }


def resolve(conn, kind: str, key: str) -> Optional[dict]:
    key = (key or "").strip().strip("/").lower()
    prefix = {"model": "/model_detail/", "make": "/manufacturer/", "variant": "/car_detail/"}[kind]
    ur = T.url_redirects
    row = conn.execute(select(ur).where(ur.c.old_path == prefix + key)).mappings().first()
    etype = eid = reason = None
    if row:
        etype, eid, reason = row["entity_type"], row["entity_id"], row["reason"]
    elif kind == "model":
        eid = conn.execute(select(T.models.c.id).where(T.models.c.slug == key, T.models.c.url_slug.isnot(None))).scalar()
        etype, reason = "model", "current"
    elif kind == "make":
        eid = conn.execute(select(T.makes.c.id).where(T.makes.c.slug == key)).scalar()
        etype, reason = "make", "current"
    elif kind == "variant" and key.isdigit():
        eid = conn.execute(select(T.cars.c.id).where(T.cars.c.id == int(key), T.cars.c.generation_id.isnot(None))).scalar()
        etype, reason = "variant", "current"
    if eid is None:
        return None
    path = entity_path(conn, etype, eid)
    if path is None:
        return None
    return {"kind": kind, "key": key, "path": path, "entity_type": etype, "entity_id": eid, "reason": reason}


def entity_path(conn, etype: str, eid: int) -> Optional[str]:
    if etype == "make":
        slug = conn.execute(select(T.makes.c.slug).where(T.makes.c.id == eid)).scalar()
        return "/make/%s" % slug if slug else None
    if etype == "model":
        row = conn.execute(select(T.makes.c.slug, T.models.c.url_slug).select_from(
            T.models.join(T.makes, T.makes.c.id == T.models.c.make_id)).where(T.models.c.id == eid)).first()
        return "/make/%s/%s" % tuple(row) if row and row[0] and row[1] else None
    if etype == "generation":
        row = conn.execute(select(T.makes.c.slug, T.models.c.url_slug, T.generations.c.slug).select_from(
            T.generations.join(T.models, T.models.c.id == T.generations.c.model_id)
            .join(T.makes, T.makes.c.id == T.models.c.make_id)).where(T.generations.c.id == eid)).first()
        return "/make/%s/%s/%s" % tuple(row) if row and all(row) else None
    if etype == "variant":
        row = conn.execute(select(T.makes.c.slug, T.models.c.url_slug, T.generations.c.slug, T.cars.c.variant_slug)
                           .select_from(T.cars.join(T.generations, T.generations.c.id == T.cars.c.generation_id)
                                        .join(T.models, T.models.c.id == T.generations.c.model_id)
                                        .join(T.makes, T.makes.c.id == T.models.c.make_id))
                           .where(T.cars.c.id == eid)).first()
        return "/make/%s/%s/%s/%s" % tuple(row) if row and all(row) else None
    return None


# ---------------------------------------------------------------- best lists

def best(conn, key: str, limit: Optional[int] = None) -> Optional[dict]:
    """GET /catalog/best/{key}: any key of the registry in services/catalog_lists.py (None if unknown)."""
    import services.catalog_lists as L  # imports this module
    return L.response(cached_catalog(conn), key, limit)


# ---------------------------------------------------------------- sitemap

def sitemap_entries(conn):
    """([(path, lastmod or None, priority)], set of model slugs) for every canonical catalog URL:
    makes, models, generations, variants, indexable version-change pages, the /compare and /best hubs,
    indexable comparison pairs (0.6, lastmod = newest change of the two models' current versions) and
    indexable lists (0.8, no lastmod)."""
    import services.catalog_changes as C  # imports this module
    import services.catalog_compare as CP
    import services.catalog_lists as L
    cat = cached_catalog(conn)
    out = [("/make", None, "0.7")]
    for make in sorted(cat.makes.values(), key=lambda k: k["slug"]):
        upd = [make["catalog_updated_at"]] + [m["updated_at"] for m in make["_models"]]
        out.append((make_path(make), max([u for u in upd if u], default=None), "0.7"))
    for m in sorted(cat.models.values(), key=lambda x: cat.model_path(x)):
        gens = cat.gens_by_model[m["id"]]
        upd = [m["updated_at"]] + [g["updated_at"] for g in gens] + \
              [v["catalog_updated_at"] for g in gens for v in cat.variants_by_gen[g["id"]]]
        out.append((cat.model_path(m), max([u for u in upd if u], default=None), "0.8"))
        for g in sorted(gens, key=S.generation_sort_key, reverse=True):
            vs = cat.variants_by_gen[g["id"]]
            if g["id"] != m["_default_gen_id"]:
                gu = [g["updated_at"]] + [v["catalog_updated_at"] for v in vs]
                out.append((cat.gen_path(g), max([u for u in gu if u], default=None), "0.6"))
            for v in sorted(vs, key=lambda x: x["variant_slug"] or ""):
                out.append((cat.variant_path(v), v["catalog_updated_at"], "0.5"))
        for older, newer in reversed(C.adjacent_pairs(gens)):
            if C.pair_quality(cat, older, newer)["indexable"]:
                out.append((C.pair_path(cat, m, older, newer), C.pair_updated(cat, older, newer), "0.6"))
    out.append(("/compare", None, "0.7"))
    for p in sorted(CP.indexable_pairs(cat), key=lambda p: p["path"]):
        out.append((p["path"], CP.pair_updated(cat, p["a"], p["b"]), "0.6"))
    out.append(("/best", None, "0.7"))
    lists = L.build_all(cat)
    for cfg in L.LISTS:
        if lists[cfg["key"]]["indexable"]:
            out.append((L.path_of(cfg["key"]), None, "0.8"))
    return out, {m["slug"] for m in cat.models.values()}
