#!/usr/bin/env python3
"""Load catalog seed files (catalog/data/{make}.json) into the catalog tables.

Idempotent upsert keyed on natural keys; a second run with the same files
changes nothing. Dry run by default (everything happens inside a transaction
that is rolled back); --apply commits.

What it writes
- makes: matched by legacy_id, else slug, else (case-insensitive) name; new makes
  are inserted with their legacy columns filled. Existing makes only get the new
  columns (slug, status_date, founded, parent_group, catalog_*, sources), plus
  make.logo.file_url into lrg_logo_img_url when that column is NULL or empty
  (an existing logo is never replaced).
- models (002 table, keyed by slug = legacy make_model_slug), model_markets,
  model_relations, generations, images.
- cars = variants. legacy_ids keep their row id: the first claimed id becomes the
  variant row and only its new columns are written (generation_id, variant_slug,
  variant_name, specs, status, sources, model_id). Further legacy ids of the same
  variant are recorded as url_redirects (merge). Variants without a legacy row
  are inserted as new cars rows (catalog_origin='seed') with legacy columns filled
  so the legacy endpoints keep working for them.
- variant_markets (offerings), url_redirects for /manufacturer, /model_detail and
  /car_detail legacy URLs.
- Within each loaded make the seed is authoritative: generations, variants,
  offerings, images, markets and relations that disappeared from the file are
  removed (legacy rows are only detached, never deleted).

Never writes a legacy column of a pre-existing row, except an empty
makes.lrg_logo_img_url (filled from make.logo, never replaced). Files that fail validation
(scripts/catalog/validate_seed.py) or conflict with an earlier file are skipped
and reported, not fatal. Files starting with "_" are skipped in a directory scan.

Usage:
  python scripts/catalog/load_seed.py                     # dry run over catalog/data
  python scripts/catalog/load_seed.py --apply
  python scripts/catalog/load_seed.py catalog/data/tesla.json --apply --report-json /tmp/r.json
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
from _common import BACKEND_DIR, guard_url, pin_env, resolve_db_url  # noqa: E402
import validate_seed  # noqa: E402

DEFAULT_DATA_DIR = os.path.join(BACKEND_DIR, "catalog", "data")
MARKET_PREFERENCE = ["US", "EU", "UK", "CN", "CA", "JP", "KR", "AU", "IN"]
VIEW_LABEL = {
    "front_3q": "front three-quarter view", "rear_3q": "rear three-quarter view",
    "side": "side view", "front": "front view", "rear": "rear view",
    "interior": "interior", "dashboard": "dashboard", "detail": "detail",
}
# ORM defaults of the legacy JSON columns (models/orm_models.py); CarRead needs reviews=[].
LEGACY_JSON_DEFAULTS = {
    "available_countries": {}, "bidirectional_details": {}, "chargers": [], "color_options": {},
    "customer_and_critic_rating": {}, "drive_assist_features": [], "speed_acc": {},
    "price_history": {}, "reviews": [], "range_details": {}, "sentry_details": {},
    "camping_features": {}, "dog_mode": {}, "infotainment_details": {},
    "interior_ambient_lighting_details": {}, "remote_heating_cooling": {}, "seating_details": {},
    "towing_details": {}, "regen_details": {}, "vehicle_sound_details": {}, "images": [],
}
LEGACY_AVAILABILITY = {  # design 4.5
    "current": ("available", True),
    "upcoming": ("Not yet released", False),
    "discontinued": ("discontinued", False),
    "cancelled": ("discontinued", False),
}


# ------------------------------------------------------------------ helpers

def _norm(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, tuple):
        return list(v)
    return v


def _same(a, b):
    a, b = _norm(a), _norm(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) \
            and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def _integral(v):
    """Legacy SubmodelInfo declares epa_range/top_speed as int; only pass integral values."""
    if v is None:
        return None
    return float(v) if float(v).is_integer() else None


class Stats:
    def __init__(self):
        self.c = defaultdict(lambda: defaultdict(int))

    def add(self, table, action, n=1):
        if n:
            self.c[table][action] += n

    def as_dict(self):
        return {t: dict(a) for t, a in sorted(self.c.items())}

    def changes(self):
        return sum(n for t in self.c.values() for a, n in t.items() if a != "unchanged")


# ------------------------------------------------------------------ loader

class SeedLoader:
    def __init__(self, conn, T, status_mod, slugs_mod):
        self.conn = conn
        self.T = T
        self.S = status_mod
        self.slugs = slugs_mod
        self.stats = Stats()
        self.warnings = []
        self.model_ids = {}          # model slug -> id (this run)
        self.loaded_make_ids = set()
        self.loaded_model_ids = set()
        self.touched_variant_ids = set()
        self.claimed = {}            # legacy id -> variant row id
        self.merged = {}             # legacy id -> primary variant row id
        self.pending_relations = []  # (model_id, relation, target slug, sources, file)
        self.desired_redirects = {}  # old_path -> (entity_type, entity_id, reason)
        self.legacy_ids = set()
        self.full_slugs = set()
        self.now = None

    # ---- generic upsert -------------------------------------------------

    def upsert(self, table, key, values, insert_extra=None, touch=None):
        """Select by key; insert or update changed columns. Returns (row, action)."""
        t = self.T.__dict__[table] if isinstance(table, str) else table
        cond = [t.c[k] == v for k, v in key.items()]
        row = self.conn.execute(t.select().where(*cond)).mappings().first()
        if row is None:
            data = dict(key)
            data.update(values)
            data.update(insert_extra or {})
            pk = list(t.primary_key.columns)
            ins = t.insert().values(**data)
            if len(pk) == 1 and pk[0].name == "id":
                new_id = self.conn.execute(ins.returning(t.c.id)).scalar()
                data["id"] = new_id
            else:
                self.conn.execute(ins)
            self.stats.add(t.name, "inserted")
            return data, "inserted"
        diff = {k: v for k, v in values.items() if not _same(row[k], v)}
        if diff:
            if touch:
                diff[touch] = self.now
            self.conn.execute(t.update().where(*cond).values(**diff))
            self.stats.add(t.name, "updated")
            merged = dict(row)
            merged.update(diff)
            return merged, "updated"
        self.stats.add(t.name, "unchanged")
        return dict(row), "unchanged"

    def warn(self, f, msg):
        self.warnings.append({"file": f, "message": msg})

    # ---- setup ----------------------------------------------------------

    def prepare(self):
        from sqlalchemy import func, select
        self.now = self.conn.execute(select(func.now())).scalar()
        cars = self.T.cars
        for cid, origin, fs in self.conn.execute(select(cars.c.id, cars.c.catalog_origin, cars.c.full_slug)):
            if origin is None:
                self.legacy_ids.add(cid)
            if fs:
                self.full_slugs.add(fs)

    # ---- make -----------------------------------------------------------

    def load_make(self, mk, f):
        from sqlalchemy import func, select
        T = self.T
        row = None
        if mk.get("legacy_id") is not None:
            row = self.conn.execute(T.makes.select().where(T.makes.c.id == mk["legacy_id"])).mappings().first()
            if row is None:
                self.warn(f, "make legacy_id %s not in database; matching by slug/name" % mk["legacy_id"])
        if row is None:
            row = self.conn.execute(T.makes.select().where(T.makes.c.slug == mk["slug"])).mappings().first()
        if row is None:
            row = self.conn.execute(T.makes.select().where(
                func.lower(T.makes.c.name) == mk["name"].lower())).mappings().first()
            if row is not None:
                self.warn(f, "make %r matched existing make id %d by name; set legacy_id" % (mk["slug"], row["id"]))
        values = {
            "slug": mk["slug"], "status_date": mk.get("status_date"), "founded": mk.get("founded"),
            "parent_group": mk.get("parent_group"), "catalog_name": mk["name"],
            "catalog_status": mk["status"], "catalog_status_details": mk.get("status_details"),
            "catalog_description": mk.get("description"), "catalog_country": mk.get("country"),
            "catalog_headquarters": mk.get("headquarters"), "catalog_website_url": mk.get("website_url"),
            "sources": mk.get("sources") or [],
        }
        logo = (mk.get("logo") or {}).get("file_url")
        if logo and row is not None and not (row["lrg_logo_img_url"] or "").strip():
            values["lrg_logo_img_url"] = logo  # fill an empty logo only; never replace one
        if row is None:
            legacy = {
                "name": mk["name"], "status": mk["status"], "status_details": mk.get("status_details"),
                "description": mk.get("description"), "website_url": mk.get("website_url"),
                "country": mk.get("country"), "headquarters": mk.get("headquarters"),
                "founding_date": str(mk["founded"]) if mk.get("founded") else None,
                "unionized": False, "catalog_origin": "seed", "catalog_updated_at": self.now,
                "lrg_logo_img_url": logo,
            }
            data, _ = self.upsert(T.makes, {"slug": mk["slug"]},
                                  {k: v for k, v in values.items() if k != "slug"}, legacy)
            make_row = data
        else:
            make_row, _ = self.upsert(T.makes, {"id": row["id"]}, values, touch="catalog_updated_at")
        self.loaded_make_ids.add(make_row["id"])
        return make_row

    # ---- model ----------------------------------------------------------

    def load_model(self, make_row, m, f):
        T = self.T
        S = self.S
        make_status = make_row["catalog_status"]
        values = {
            "make_id": make_row["id"], "name": m["name"], "body_style": m["body_style"],
            "status": m["status"], "description": m.get("description"),
            "official_url": m.get("official_url"), "sources": m.get("sources") or [],
            "url_slug": m["url_slug"], "aliases": m.get("aliases") or [],
            "is_commercial": bool(m.get("is_commercial")),
        }
        model_row, _ = self.upsert(T.models, {"slug": m["slug"]}, values,
                                   {"catalog_origin": "seed"}, touch="updated_at")
        mid = model_row["id"]
        self.model_ids[m["slug"]] = mid
        self.loaded_model_ids.add(mid)

        # markets
        want = {}
        for code, mv in (m.get("markets") or {}).items():
            want[code] = mv
            self.upsert(T.model_markets, {"model_id": mid, "market": code}, {
                "status": mv["status"], "local_name": mv.get("local_name"),
                "launch_date": mv.get("launch"), "end_date": mv.get("end"),
                "basis": "seed", "sources": m.get("sources") or [],
            }, touch="updated_at")
        self._delete_missing(T.model_markets, T.model_markets.c.model_id == mid,
                             T.model_markets.c.market, list(want))

        for r in m.get("relations") or []:
            self.pending_relations.append((mid, r["relation"], r["model"], f))

        # statuses, default generation
        model_eff = S.model_status(m["status"], make_status)
        gens = m.get("generations") or []
        gen_eff = {g["slug"]: S.generation_status(g["status"], model_eff, make_status) for g in gens}
        default = S.default_generation(
            [dict(slug=g["slug"], start_year=g.get("start_year"), ordinal=g.get("ordinal"),
                  status=gen_eff[g["slug"]]) for g in gens])
        default_slug = default["slug"] if default else None

        gen_ids = []
        for g in gens:
            gid = self.load_generation(make_row, m, mid, g, f)
            gen_ids.append(gid)
            for order, v in enumerate(g.get("variants") or []):
                v["_order"] = order
                v_eff = S.variant_status(v.get("status"), g["status"], gen_eff[g["slug"]], make_status)
                self.load_variant(make_row, m, mid, g, gid, v, v_eff,
                                  g["slug"] == default_slug, f)

        # stale generations / variants of this model
        from sqlalchemy import select
        gq = select(T.generations.c.id).where(T.generations.c.model_id == mid)
        stale_gens = [r[0] for r in self.conn.execute(gq) if r[0] not in gen_ids]
        all_gens = gen_ids + stale_gens
        if all_gens:
            rows = self.conn.execute(select(T.cars.c.id).where(T.cars.c.generation_id.in_(all_gens)))
            self._detach_variants([r[0] for r in rows if r[0] not in self.touched_variant_ids])
        if stale_gens:
            self.conn.execute(T.generations.delete().where(T.generations.c.id.in_(stale_gens)))
            self.stats.add("generations", "deleted", len(stale_gens))
        return mid

    def _delete_missing(self, table, scope_cond, key_col, keep):
        q = table.delete().where(scope_cond)
        if keep:
            q = q.where(key_col.notin_(keep))
        n = self.conn.execute(q).rowcount
        self.stats.add(table.name, "deleted", n)

    def _detach_variants(self, ids):
        """Seed-created rows are deleted; legacy rows only lose their catalog placement."""
        if not ids:
            return
        T = self.T
        from sqlalchemy import select
        rows = self.conn.execute(select(T.cars.c.id, T.cars.c.catalog_origin).where(T.cars.c.id.in_(ids))).all()
        seed_ids = [r[0] for r in rows if r[1] == "seed"]
        legacy_ids = [r[0] for r in rows if r[1] is None]
        if legacy_ids:
            n = self.conn.execute(T.variant_markets.delete().where(T.variant_markets.c.car_id.in_(legacy_ids))).rowcount
            self.stats.add("variant_markets", "deleted", n)
            self.conn.execute(T.cars.update().where(T.cars.c.id.in_(legacy_ids)).values(
                generation_id=None, variant_slug=None, catalog_updated_at=self.now))
            self.stats.add("cars", "detached", len(legacy_ids))
        if seed_ids:
            self.conn.execute(T.cars.delete().where(T.cars.c.id.in_(seed_ids)))
            self.stats.add("cars", "deleted", len(seed_ids))

    # ---- generation + images ---------------------------------------------

    def load_generation(self, make_row, m, mid, g, f):
        T = self.T
        row, _ = self.upsert(T.generations, {"model_id": mid, "slug": g["slug"]}, {
            "name": g["name"], "kind": g["kind"], "ordinal": g.get("ordinal"),
            "code_name": g.get("code_name"), "platform": g.get("platform"),
            "start_year": g.get("start_year"), "end_year": g.get("end_year"),
            "status": g["status"], "description": g.get("description"),
            "sources": g.get("sources") or [],
        }, touch="updated_at")
        gid = row["id"]

        imgs, seen = [], set()
        for im in g.get("images") or []:
            if im["file_url"] in seen:
                self.warn(f, "%s/%s: duplicate image %s skipped" % (m["slug"], g["slug"], im["file_url"]))
                continue
            seen.add(im["file_url"])
            imgs.append(im)
        primary = self._pick_primary(imgs)
        # clear a primary flag that moves, before upserting (one primary per generation)
        q = T.images.update().where(T.images.c.generation_id == gid, T.images.c.is_primary.is_(True))
        if primary is not None:
            q = q.where(T.images.c.file_url != primary["file_url"])
        self.conn.execute(q.values(is_primary=False))
        years = "%s" % g.get("start_year") if g.get("start_year") else ""
        for i, im in enumerate(imgs):
            view = VIEW_LABEL.get(im.get("view") or "", None)
            alt = "%s %s (%s%s)%s" % (make_row["catalog_name"], m["name"], g["name"],
                                      ", " + years if years else "", ", " + view if view else "")
            self.upsert(T.images, {"generation_id": gid, "file_url": im["file_url"]}, {
                "model_id": mid, "source": im["source"], "page_url": im.get("page_url"),
                "credit": im.get("credit"), "license": im.get("license"), "view": im.get("view"),
                "verified": im.get("verified_by_viewing") is True,
                "is_primary": primary is not None and im is primary,
                "sort_order": i, "alt_text": alt[:125],
            }, touch="updated_at")
        self._delete_missing(T.images, T.images.c.generation_id == gid, T.images.c.file_url,
                             [im["file_url"] for im in imgs])
        return gid

    @staticmethod
    def _pick_primary(imgs):
        ok = [im for im in imgs if im.get("verified_by_viewing") is True]
        for view in ("front_3q", "side", "front"):
            for im in ok:
                if im.get("view") == view:
                    return im
        return ok[0] if ok else None

    # ---- variant + offerings ---------------------------------------------

    def load_variant(self, make_row, m, mid, g, gid, v, v_eff, in_default_gen, f):
        from sqlalchemy import select
        T = self.T
        cars = T.cars
        key = "%s/%s/%s" % (m["slug"], g["slug"], v["slug"])

        primary = None
        for lid in v.get("legacy_ids") or []:
            if lid in self.claimed or lid in self.merged:
                self.warn(f, "%s: legacy id %d already claimed in this run; ignored" % (key, lid))
                continue
            if lid not in self.legacy_ids:
                self.warn(f, "%s: legacy id %d is not a legacy cars row; ignored" % (key, lid))
                continue
            if primary is None:
                primary = lid
                self.claimed[lid] = lid
            else:
                self.merged[lid] = primary

        # whoever holds (generation, slug) now but is not the target gets moved out
        holder = self.conn.execute(select(cars.c.id, cars.c.catalog_origin).where(
            cars.c.generation_id == gid, cars.c.variant_slug == v["slug"])).first()

        catalog_vals = {
            "generation_id": gid, "variant_slug": v["slug"], "variant_name": v["name"],
            "status": v.get("status"), "year_from": v.get("year_from"), "year_to": v.get("year_to"),
            "drivetrain": v.get("drivetrain"), "body_type": v.get("body_type"), "seats": v.get("seats"),
            "battery_kwh": v.get("battery_kwh"), "battery_basis": v.get("battery_basis"),
            "power_hp": v.get("power_hp"), "torque_lbft": v.get("torque_lbft"),
            "accel_0_60_s": v.get("accel_0_60_s"), "accel_0_100_s": v.get("accel_0_100_s"),
            "top_speed_mph": v.get("top_speed_mph"), "dc_kw": v.get("dc_kw"),
            "sources": v.get("sources") or [], "model_id": mid, "variant_order": v.get("_order"),
        }

        if primary is not None:
            if holder is not None and holder[0] != primary:
                self._detach_variants([holder[0]])
            if make_row["id"] != self._car_make(primary):
                self.warn(f, "%s: legacy id %d belongs to another make" % (key, primary))
            row, _ = self.upsert(cars, {"id": primary}, catalog_vals, touch="catalog_updated_at")
            car_id = primary
        else:
            target = None
            if holder is not None and holder[1] == "seed":
                target = holder[0]
            elif holder is not None:
                # a legacy row holds this slug but the seed no longer claims it
                self._detach_variants([holder[0]])
            legacy_vals = self._legacy_cache(make_row, m, g, v, v_eff, in_default_gen, gid)
            if target is None:
                fs = self.slugs.variant_full_slug(make_row["slug"], m["url_slug"], g["slug"], v["slug"],
                                                  self.full_slugs)
                self.full_slugs.add(fs)
                data = dict(catalog_vals)
                data.update(legacy_vals)
                data.update(LEGACY_JSON_DEFAULTS)
                data.update({"full_slug": fs, "is_model_rep": False, "catalog_origin": "seed",
                             "catalog_updated_at": self.now})
                car_id = self.conn.execute(cars.insert().values(**data).returning(cars.c.id)).scalar()
                self.stats.add("cars", "inserted")
            else:
                vals = dict(catalog_vals)
                vals.update(legacy_vals)
                self.upsert(cars, {"id": target}, vals, touch="catalog_updated_at")
                car_id = target
        self.touched_variant_ids.add(car_id)

        # offerings
        keep = []
        for o in v.get("offerings") or []:
            mk = (o["market"], o.get("model_year"))
            keep.append(mk)
            vm = T.variant_markets
            cond = [vm.c.car_id == car_id, vm.c.market == o["market"],
                    vm.c.model_year.is_(None) if o.get("model_year") is None else vm.c.model_year == o["model_year"]]
            vals = {
                "currency": o.get("currency"), "current_price": o.get("price"),
                "launch_price": o.get("launch_price"), "price_basis": o.get("price_basis"),
                "range_value": o.get("range"), "range_unit": o.get("range_unit"),
                "range_cycle": o.get("range_cycle"), "connector": o.get("connector"),
                "is_estimate": bool(o.get("is_estimate")),
            }
            row = self.conn.execute(vm.select().where(*cond)).mappings().first()
            if row is None:
                self.conn.execute(vm.insert().values(car_id=car_id, market=o["market"],
                                                     model_year=o.get("model_year"), **vals))
                self.stats.add("variant_markets", "inserted")
            else:
                diff = {k: x for k, x in vals.items() if not _same(row[k], x)}
                if diff:
                    diff["updated_at"] = self.now
                    self.conn.execute(vm.update().where(vm.c.id == row["id"]).values(**diff))
                    self.stats.add("variant_markets", "updated")
                else:
                    self.stats.add("variant_markets", "unchanged")
        existing = self.conn.execute(select(T.variant_markets.c.id, T.variant_markets.c.market,
                                            T.variant_markets.c.model_year)
                                     .where(T.variant_markets.c.car_id == car_id)).all()
        stale = [r[0] for r in existing if (r[1], r[2]) not in keep]
        if stale:
            self.conn.execute(T.variant_markets.delete().where(T.variant_markets.c.id.in_(stale)))
            self.stats.add("variant_markets", "deleted", len(stale))

        # legacy URLs
        if primary is not None:
            self.desired_redirects["/car_detail/%d" % primary] = ("variant", car_id, "legacy")
        for lid, p in self.merged.items():
            if p == primary and primary is not None:
                self.desired_redirects["/car_detail/%d" % lid] = ("variant", car_id, "merge")
        return car_id

    def _car_make(self, car_id):
        from sqlalchemy import select
        return self.conn.execute(select(self.T.cars.c.make_id).where(self.T.cars.c.id == car_id)).scalar()

    def _legacy_cache(self, make_row, m, g, v, v_eff, in_default_gen, gid):
        """Legacy columns for a seed-created row, derived from seed facts only (design 4.5)."""
        from sqlalchemy import select
        T = self.T
        desc, avail = LEGACY_AVAILABILITY.get(v_eff, (None, None))
        if not in_default_gen:
            desc = "previous_generation"
        us = [o for o in (v.get("offerings") or []) if o["market"] == "US"]
        us.sort(key=lambda o: (o.get("model_year") or 0), reverse=True)
        epa = next((o["range"] for o in us if o.get("range") is not None and o.get("range_cycle") == "EPA"), None)
        usd = next((o["price"] for o in us if o.get("price") is not None and o.get("currency") == "USD"), None)
        img = self.conn.execute(select(T.images.c.file_url).where(
            T.images.c.generation_id == gid, T.images.c.is_primary.is_(True),
            T.images.c.verified.is_(True))).scalar()
        return {
            "make_id": make_row["id"], "make_name": make_row.get("name") or make_row["catalog_name"],
            "model": m["name"], "submodel": v["name"], "generation": g["slug"],
            "make_model_slug": m["slug"], "model_webpage": m.get("official_url"),
            "model_description": m.get("description"),
            "availability_desc": desc, "production_availability": avail,
            "battery_capacity": v.get("battery_kwh"), "battery_max_charging_speed": v.get("dc_kw"),
            "acceleration_0_60": v.get("accel_0_60_s"), "power": v.get("power_hp"),
            "torque": v.get("torque_lbft"), "top_speed": _integral(v.get("top_speed_mph")),
            "number_of_full_adult_seats": v.get("seats"), "drive_type": v.get("drivetrain"),
            "vehicle_class": v.get("body_type") or m["body_style"],
            "epa_range": _integral(epa), "current_price": usd, "image_url": img,
        }

    # ---- after all files ------------------------------------------------

    def finish(self, make_files):
        from sqlalchemy import select
        T = self.T
        # retire models of loaded makes that are no longer in their file
        for make_id, slugs in make_files.items():
            rows = self.conn.execute(select(T.models.c.id, T.models.c.slug).where(
                T.models.c.make_id == make_id, T.models.c.url_slug.isnot(None))).all()
            for mid, slug in rows:
                if slug in slugs:
                    continue
                gens = [r[0] for r in self.conn.execute(select(T.generations.c.id).where(
                    T.generations.c.model_id == mid))]
                if gens:
                    vids = [r[0] for r in self.conn.execute(select(T.cars.c.id).where(
                        T.cars.c.generation_id.in_(gens)))]
                    self._detach_variants(vids)
                    self.conn.execute(T.generations.delete().where(T.generations.c.id.in_(gens)))
                    self.stats.add("generations", "deleted", len(gens))
                self.conn.execute(T.model_markets.delete().where(T.model_markets.c.model_id == mid))
                self.conn.execute(T.models.update().where(T.models.c.id == mid).values(
                    url_slug=None, updated_at=self.now))
                self.stats.add("models", "retired")
                self.warnings.append({"file": "-", "message": "model %s retired (no longer in its make file)" % slug})

        # relations
        want = defaultdict(set)
        for mid, rel, target, f in self.pending_relations:
            tid = self.model_ids.get(target)
            if tid is None:
                tid = self.conn.execute(select(T.models.c.id).where(
                    T.models.c.slug == target, T.models.c.url_slug.isnot(None))).scalar()
            if tid is None:
                self.warn(f, "relation target %r not loaded; skipped" % target)
                continue
            if tid == mid:
                continue
            want[mid].add((tid, rel))
            self.upsert(T.model_relations, {"model_id": mid, "related_model_id": tid, "relation": rel},
                        {"sources": []})
        for mid in self.loaded_model_ids:
            rows = self.conn.execute(select(T.model_relations.c.related_model_id, T.model_relations.c.relation)
                                     .where(T.model_relations.c.model_id == mid)).all()
            for tid, rel in rows:
                if (tid, rel) not in want[mid]:
                    self.conn.execute(T.model_relations.delete().where(
                        T.model_relations.c.model_id == mid, T.model_relations.c.related_model_id == tid,
                        T.model_relations.c.relation == rel))
                    self.stats.add("model_relations", "deleted")

        self._redirects()

    def _redirects(self):
        from sqlalchemy import select
        T = self.T
        cars = T.cars
        # makes: the frontend's legacy slug of the legacy name, the seed slug, the raw lowercase name
        for mrow in self.conn.execute(select(T.makes.c.id, T.makes.c.name, T.makes.c.slug,
                                             T.makes.c.catalog_origin)
                                      .where(T.makes.c.id.in_(self.loaded_make_ids))):
            mid, name, slug, origin = mrow
            if origin is None:
                self.desired_redirects["/manufacturer/%s" % self.slugs.legacy_make_path_slug(name)] = \
                    ("make", mid, "legacy")
                raw = "-".join((name or "").lower().split())
                self.desired_redirects.setdefault("/manufacturer/%s" % raw, ("make", mid, "alias"))
            self.desired_redirects.setdefault("/manufacturer/%s" % slug, ("make", mid, "alias"))
        # models: every legacy make_model_slug of a claimed row -> the model of its variant
        claimed_rows = list(self.claimed) + list(self.merged)
        if claimed_rows:
            rows = self.conn.execute(select(cars.c.id, cars.c.make_model_slug).where(cars.c.id.in_(claimed_rows))).all()
            variant_model = dict(self.conn.execute(select(cars.c.id, cars.c.model_id).where(
                cars.c.id.in_(list(self.claimed)))).all())
            votes = defaultdict(lambda: defaultdict(int))
            for cid, mms in rows:
                if not mms:
                    continue
                vid = self.claimed.get(cid) or self.merged.get(cid)
                model_id = variant_model.get(vid)
                if model_id:
                    votes[mms.strip().lower()][model_id] += 1
            slug_of = {v: k for k, v in self.model_ids.items()}
            for mms, cands in votes.items():
                exact = [mid for mid in cands if slug_of.get(mid) == mms]
                target = exact[0] if exact else max(cands, key=lambda k: cands[k])
                reason = "legacy" if exact else "merge"
                self.desired_redirects["/model_detail/%s" % mms] = ("model", target, reason)

        # diff against rows that point into the loaded makes (or share a desired path)
        ur = T.url_redirects
        existing = {r["old_path"]: r for r in self.conn.execute(ur.select()).mappings()}
        in_scope = self._entities_in_loaded_makes()
        for path, (etype, eid, reason) in self.desired_redirects.items():
            cur = existing.get(path)
            if cur is None:
                self.conn.execute(ur.insert().values(old_path=path, entity_type=etype, entity_id=eid, reason=reason))
                self.stats.add("url_redirects", "inserted")
            elif (cur["entity_type"], cur["entity_id"], cur["reason"]) != (etype, eid, reason):
                self.conn.execute(ur.update().where(ur.c.old_path == path).values(
                    entity_type=etype, entity_id=eid, reason=reason))
                self.stats.add("url_redirects", "updated")
            else:
                self.stats.add("url_redirects", "unchanged")
        stale = [p for p, r in existing.items()
                 if p not in self.desired_redirects and (r["entity_type"], r["entity_id"]) in in_scope]
        if stale:
            self.conn.execute(ur.delete().where(ur.c.old_path.in_(stale)))
            self.stats.add("url_redirects", "deleted", len(stale))
        # anything pointing at an entity that is no longer in the catalog
        from sqlalchemy import text
        n = self.conn.execute(text("""
            DELETE FROM url_redirects r WHERE
              (r.entity_type = 'variant' AND NOT EXISTS (SELECT 1 FROM cars c WHERE c.id = r.entity_id AND c.generation_id IS NOT NULL))
           OR (r.entity_type = 'model' AND NOT EXISTS (SELECT 1 FROM models m WHERE m.id = r.entity_id AND m.url_slug IS NOT NULL))
           OR (r.entity_type = 'make' AND NOT EXISTS (SELECT 1 FROM makes k WHERE k.id = r.entity_id AND k.slug IS NOT NULL))
           OR (r.entity_type = 'generation' AND NOT EXISTS (SELECT 1 FROM generations g WHERE g.id = r.entity_id))
        """)).rowcount
        self.stats.add("url_redirects", "deleted", n)

    def _entities_in_loaded_makes(self):
        from sqlalchemy import select
        T = self.T
        out = {("make", i) for i in self.loaded_make_ids}
        mids = [r[0] for r in self.conn.execute(select(T.models.c.id).where(T.models.c.make_id.in_(self.loaded_make_ids)))]
        out |= {("model", i) for i in mids}
        if mids:
            vids = self.conn.execute(select(T.cars.c.id).where(T.cars.c.model_id.in_(mids))).all()
            out |= {("variant", r[0]) for r in vids}
        return out

    def unclaimed_report(self):
        """Legacy rows that are neither a variant nor merged into one, grouped by make."""
        from sqlalchemy import text
        merged = set(self.merged)
        rows = self.conn.execute(text(
            "SELECT c.id, coalesce(k.name, c.make_name), c.model, c.submodel, c.make_id "
            "FROM cars c LEFT JOIN makes k ON k.id = c.make_id "
            "WHERE c.catalog_origin IS NULL AND c.generation_id IS NULL ORDER BY 2, 1")).all()
        # merged legacy rows from earlier runs are recorded only in url_redirects
        prior = {int(p.rsplit("/", 1)[1]) for (p,) in self.conn.execute(text(
            "SELECT old_path FROM url_redirects WHERE reason = 'merge' AND old_path LIKE '/car_detail/%'"))}
        out = defaultdict(list)
        for cid, make, model, sub, make_id in rows:
            if cid in merged or cid in prior:
                continue
            out[make or "?"].append({"id": cid, "model": model, "submodel": (sub or "").strip(),
                                     "make_loaded": make_id in self.loaded_make_ids})
        return dict(out)


# ------------------------------------------------------------------ driver

def expand(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for n in sorted(os.listdir(p)):
                if n.endswith(".json") and not n.startswith("_"):
                    files.append(os.path.join(p, n))
        else:
            files.append(p)
    return files


def validate_files(files):
    """Returns (accepted [(path, doc)], skipped [{file, reason, errors}])."""
    accepted, skipped = [], []
    seen_make, seen_make_id, seen_model, seen_claim = {}, {}, {}, {}
    for path in files:
        rep = validate_seed.Report()
        doc, ok = validate_seed.load_json(path, rep)
        if not ok:
            skipped.append({"file": path, "reason": "unreadable", "errors": rep.errors[:10]})
            continue
        fc = validate_seed.FileCheck(rep, path)
        fc.run(doc)
        if rep.errors:
            skipped.append({"file": path, "reason": "validation failed (%d errors)" % len(rep.errors),
                            "errors": rep.errors[:10]})
            continue
        conflicts = []
        mk = doc["make"]
        if mk["slug"] in seen_make:
            conflicts.append("make slug %r also in %s" % (mk["slug"], seen_make[mk["slug"]]))
        if mk.get("legacy_id") is not None and mk["legacy_id"] in seen_make_id:
            conflicts.append("make legacy_id %d also in %s" % (mk["legacy_id"], seen_make_id[mk["legacy_id"]]))
        for s in fc.model_slugs:
            if s in seen_model:
                conflicts.append("model slug %r also in %s" % (s, seen_model[s]))
        for lid in fc.claims:
            if lid in seen_claim:
                conflicts.append("legacy id %d also claimed in %s" % (lid, seen_claim[lid]))
        if conflicts:
            skipped.append({"file": path, "reason": "conflicts with an earlier file", "errors": conflicts[:10]})
            continue
        seen_make[mk["slug"]] = path
        if mk.get("legacy_id") is not None:
            seen_make_id[mk["legacy_id"]] = path
        for s in fc.model_slugs:
            seen_model[s] = path
        for lid in fc.claims:
            seen_claim[lid] = path
        accepted.append((path, doc))
    return accepted, skipped


def run(conn, files):
    """Load files on an open connection (caller owns the transaction). Returns the report dict."""
    import services.catalog_tables as T
    import services.catalog_status as S
    import services.catalog_slugs as slugs

    accepted, skipped = validate_files(files)
    loader = SeedLoader(conn, T, S, slugs)
    loader.prepare()
    make_files = {}
    for path, doc in accepted:
        f = os.path.basename(path)
        make_row = loader.load_make(doc["make"], f)
        for m in doc["models"]:
            loader.load_model(make_row, m, f)
        make_files[make_row["id"]] = {m["slug"] for m in doc["models"]}
    loader.finish(make_files)
    return {
        "files_loaded": [os.path.basename(p) for p, _ in accepted],
        "files_skipped": skipped,
        "stats": loader.stats.as_dict(),
        "changes": loader.stats.changes(),
        "warnings": loader.warnings,
        "unclaimed_legacy": loader.unclaimed_report(),
        "merged_legacy": {str(k): v for k, v in sorted(loader.merged.items())},
    }


def _print_report(r, applied):
    print("%s: %d file(s) loaded, %d skipped, %d row change(s)" % (
        "APPLIED" if applied else "DRY RUN (rolled back; pass --apply to write)",
        len(r["files_loaded"]), len(r["files_skipped"]), r["changes"]))
    for t, acts in r["stats"].items():
        print("  %-16s %s" % (t, ", ".join("%s %d" % kv for kv in sorted(acts.items()))))
    for s in r["files_skipped"]:
        print("SKIPPED %s: %s" % (s["file"], s["reason"]))
        for e in s["errors"][:5]:
            print("    %s" % (e if isinstance(e, str) else "%s: %s" % (e.get("path"), e.get("message"))))
    for w in r["warnings"]:
        print("WARN %s: %s" % (w["file"], w["message"]))
    un = r["unclaimed_legacy"]
    total = sum(len(v) for v in un.values())
    print("Unclaimed legacy cars rows: %d" % total)
    for make, rows in sorted(un.items()):
        flag = " (make loaded!)" if any(x["make_loaded"] for x in rows) else ""
        print("  %s%s: %s" % (make, flag, ", ".join(str(x["id"]) for x in rows)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=[DEFAULT_DATA_DIR])
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    ap.add_argument("--db-url")
    ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--report-json", help="also write the full report here")
    args = ap.parse_args(argv)

    url = resolve_db_url(args.db_url)
    guard_url(url, args.allow_remote)
    pin_env(url)
    from sqlalchemy import create_engine, text

    files = expand(args.paths or [DEFAULT_DATA_DIR])
    engine = create_engine(url)
    with engine.connect() as conn:
        missing = conn.execute(text("SELECT to_regclass('public.generations') IS NULL")).scalar()
        conn.rollback()
        if missing:
            sys.exit("catalog tables missing: run `alembic upgrade head` first")
        trans = conn.begin()
        try:
            report = run(conn, files)
            if args.apply:
                trans.commit()
            else:
                trans.rollback()
        except Exception:
            trans.rollback()
            raise
    _print_report(report, args.apply)
    if args.report_json:
        with open(args.report_json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
