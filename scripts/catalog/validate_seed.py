#!/usr/bin/env python3
"""Validate EV Lineup catalog seed files (ev_backend/catalog/data/{make_slug}.json).

Stdlib only; runs on Python 3.9+.

Usage:
  python3 ev_backend/scripts/catalog/validate_seed.py FILE_OR_DIR [FILE_OR_DIR ...]
      [--legacy _catalog_work/legacy/tesla.json ...] [--json]

A directory expands to its *.json files, skipping names that start with "_"
(the same rule the loader uses). Files named explicitly are always validated.
Errors exit 1; warnings (plausibility, cross-file references) never fail.
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- enums ----

MAKE_STATUS = {"active", "pre-production", "defunct", "acquired"}
LIFECYCLE = {"upcoming", "current", "discontinued", "cancelled"}
BODY = {"sedan", "hatchback", "wagon", "coupe", "convertible", "suv",
        "pickup", "van", "minivan", "microcar"}
MARKETS = {"US", "CA", "EU", "UK", "CN", "JP", "KR", "IN", "AU"}
RELATIONS = {"twin", "successor"}
GEN_KIND = {"generation", "refresh"}
IMG_SOURCE = {"commons", "press", "legacy"}
IMG_VIEW = {"front_3q", "rear_3q", "side", "front", "rear", "interior",
            "dashboard", "detail"}
DRIVETRAIN = {"FWD", "RWD", "AWD"}
BATTERY_BASIS = {"usable", "gross"}
RANGE_CYCLE_UNIT = {"EPA": "mi", "WLTP": "km", "CLTC": "km", "WLTC": "km",
                    "KR": "km", "MIDC": "km"}
PRICE_BASIS = {"msrp_excl_destination", "msrp_incl_destination", "list_incl_vat"}
CONNECTOR = {"NACS", "CCS1", "CCS2", "GBT", "CHADEMO"}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GEN_SLUG_RE = re.compile(r"^[0-9]{4}(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
URL_RE = re.compile(r"^https?://\S+$")
LEGACY_IMG_PREFIX = "/pub_assets/car_images/"

YEAR_MIN, YEAR_MAX = 1990, 2035

# ------------------------------------------------------------- key sets ----
# required = must be present and non-null; optional = may be absent or null.

TOP_REQ = {"make", "models"}
TOP_OPT = {"legacy_notes", "gaps"}
MAKE_REQ = {"slug", "name", "status"}
MAKE_OPT = {"legacy_id", "country", "headquarters", "founded", "parent_group",
            "website_url", "status_date", "status_details", "description", "sources"}
MODEL_REQ = {"slug", "url_slug", "name", "body_style", "status", "generations"}
MODEL_OPT = {"aliases", "is_commercial", "official_url", "description",
             "markets", "relations", "sources"}
MARKET_REQ = {"status"}
MARKET_OPT = {"launch", "end", "local_name"}
RELATION_REQ = {"relation", "model"}
GEN_REQ = {"slug", "name", "kind", "start_year", "status", "variants"}
GEN_OPT = {"ordinal", "code_name", "platform", "end_year", "description",
           "images", "sources"}
IMG_REQ = {"source", "file_url"}
IMG_OPT = {"page_url", "credit", "license", "view", "verified_by_viewing"}
VAR_REQ = {"slug", "name", "sources"}
VAR_OPT = {"legacy_ids", "status", "year_from", "year_to", "drivetrain",
           "body_type", "seats", "battery_kwh", "battery_basis", "power_hp",
           "torque_lbft", "accel_0_60_s", "accel_0_100_s", "top_speed_mph",
           "dc_kw", "offerings"}
OFF_REQ = {"market"}
OFF_OPT = {"model_year", "range", "range_unit", "range_cycle", "price",
           "launch_price", "currency", "price_basis", "connector", "is_estimate"}
SRC_REQ = {"url"}
SRC_OPT = {"fields", "name"}
NOTE_REQ = {"legacy_id", "note"}

# (field, low, high) plausible bounds -> warnings only
VARIANT_BOUNDS = [
    ("accel_0_60_s", 1.5, 20), ("accel_0_100_s", 1.5, 20),
    ("battery_kwh", 5, 250), ("dc_kw", 3, 1000), ("power_hp", 10, 2500),
    ("torque_lbft", 20, 2500), ("top_speed_mph", 30, 300), ("seats", 1, 9),
]


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.counts = {"files": 0, "makes": 0, "models": 0, "generations": 0,
                       "variants": 0, "offerings": 0, "images": 0}

    def err(self, file, path, msg):
        self.errors.append({"file": file, "path": path, "message": msg})

    def warn(self, file, path, msg):
        self.warnings.append({"file": file, "path": path, "message": msg})


# ------------------------------------------------------------- helpers ----

def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_str(v):
    return isinstance(v, str) and v.strip() != ""


def valid_date(s):
    m = DATE_RE.match(s) if isinstance(s, str) else None
    if not m:
        return False
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if not YEAR_MIN - 200 <= int(y) <= YEAR_MAX:
        return False
    if mo is not None and not 1 <= int(mo) <= 12:
        return False
    if d is not None and not 1 <= int(d) <= 31:
        return False
    return True


class FileCheck:
    """Validates one parsed seed document."""

    def __init__(self, rep, fname):
        self.rep = rep
        self.f = fname
        self.make_slug = None
        self.model_slugs = {}      # slug -> path
        self.claims = {}           # legacy car id -> path
        self.relation_refs = []    # (path, target slug)
        self.make_legacy_id = None

    def e(self, path, msg):
        self.rep.err(self.f, path, msg)

    def w(self, path, msg):
        self.rep.warn(self.f, path, msg)

    # ---- generic

    def obj(self, v, path, req, opt):
        """Check v is an object with required non-null keys and no unknown keys."""
        if not isinstance(v, dict):
            self.e(path, "expected an object, got %s" % type(v).__name__)
            return False
        for k in sorted(req):
            if k not in v:
                self.e(path, "missing required key '%s'" % k)
            elif v[k] is None:
                self.e("%s.%s" % (path, k), "required key is null")
        for k in sorted(set(v) - req - opt):
            self.e("%s.%s" % (path, k), "unknown key '%s'" % k)
        return True

    def lst(self, v, path, allow_none=True):
        if v is None:
            if not allow_none:
                self.e(path, "expected an array, got null")
            return []
        if not isinstance(v, list):
            self.e(path, "expected an array, got %s" % type(v).__name__)
            return []
        return v

    def enum(self, v, path, allowed):
        if v is None:
            return  # presence is enforced by obj() for required keys
        if v not in allowed:
            self.e(path, "invalid value %r; expected one of %s"
                   % (v, ", ".join(sorted(allowed))))

    def string(self, v, path):
        if v is not None and not is_str(v):
            self.e(path, "expected a non-empty string, got %r" % (v,))

    def url(self, v, path):
        if v is None:
            return
        if not isinstance(v, str) or not URL_RE.match(v):
            self.e(path, "expected an http(s) URL, got %r" % (v,))

    def date(self, v, path):
        if v is not None and not valid_date(v):
            self.e(path, "expected 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD', got %r" % (v,))

    def year(self, v, path, lo=YEAR_MIN, hi=YEAR_MAX):
        if v is None:
            return
        if not is_int(v):
            self.e(path, "expected an integer year, got %r" % (v,))
        elif not lo <= v <= hi:
            self.e(path, "year %d out of range %d-%d" % (v, lo, hi))

    def number(self, v, path, positive=True):
        if v is None:
            return False
        if not is_num(v):
            self.e(path, "expected a number, got %r" % (v,))
            return False
        if positive and v <= 0:
            self.e(path, "expected a positive number, got %r" % (v,))
            return False
        return True

    def bounds(self, v, path, lo, hi, label):
        if is_num(v) and not lo <= v <= hi:
            self.w(path, "%s %r outside plausible range %s-%s" % (label, v, lo, hi))

    def boolean(self, v, path):
        if v is not None and not isinstance(v, bool):
            self.e(path, "expected true/false, got %r" % (v,))

    def slug(self, v, path, pattern=SLUG_RE, hint="lowercase [a-z0-9-]"):
        if v is None:
            return
        if not isinstance(v, str) or not pattern.match(v):
            self.e(path, "invalid slug %r (%s)" % (v, hint))

    def year_order(self, a, b, path, la, lb):
        if is_int(a) and is_int(b) and a > b:
            self.e(path, "%s (%d) is after %s (%d)" % (la, a, lb, b))

    # ---- sources

    def sources(self, v, path, nonempty=False):
        items = self.lst(v, path)
        out = []
        for i, s in enumerate(items):
            p = "%s[%d]" % (path, i)
            if not self.obj(s, p, SRC_REQ, SRC_OPT):
                continue
            self.url(s.get("url"), p + ".url")
            self.string(s.get("name"), p + ".name")
            fields = self.lst(s.get("fields"), p + ".fields")
            for j, fl in enumerate(fields):
                if not is_str(fl):
                    self.e("%s.fields[%d]" % (p, j), "expected a non-empty string")
            if isinstance(s.get("url"), str) and URL_RE.match(s["url"]):
                out.append(s)
        if nonempty and not out:
            self.e(path, "at least one source with a URL is required")
        return out

    def needs_status_source(self, srcs, path, what):
        covered = [s for s in srcs
                   if isinstance(s.get("fields"), list) and "status" in s["fields"]]
        if not covered:
            self.e(path, "%s needs a source with \"status\" in its fields" % what)

    # ---- document

    def run(self, doc):
        if not self.obj(doc, "$", TOP_REQ, TOP_OPT):
            return
        self.make(doc.get("make"), "$.make")
        models = self.lst(doc.get("models"), "$.models", allow_none=False)
        url_slugs = {}
        for i, m in enumerate(models):
            self.model(m, "$.models[%d]" % i, url_slugs)
        for i, n in enumerate(self.lst(doc.get("legacy_notes"), "$.legacy_notes")):
            p = "$.legacy_notes[%d]" % i
            if self.obj(n, p, NOTE_REQ, set()):
                if not is_int(n.get("legacy_id")):
                    self.e(p + ".legacy_id", "expected an integer")
                self.string(n.get("note"), p + ".note")
        for i, g in enumerate(self.lst(doc.get("gaps"), "$.gaps")):
            if not is_str(g):
                self.e("$.gaps[%d]" % i, "expected a non-empty string")

    def make(self, mk, path):
        if not self.obj(mk, path, MAKE_REQ, MAKE_OPT):
            return
        self.rep.counts["makes"] += 1
        self.slug(mk.get("slug"), path + ".slug")
        if isinstance(mk.get("slug"), str):
            self.make_slug = mk["slug"]
            base = os.path.splitext(os.path.basename(self.f))[0]
            if base != mk["slug"] and not base.startswith("_"):
                self.w(path + ".slug", "file name '%s' does not match make slug '%s'"
                       % (base, mk["slug"]))
        self.string(mk.get("name"), path + ".name")
        if is_int(mk.get("legacy_id")):
            self.make_legacy_id = mk["legacy_id"]
        elif mk.get("legacy_id") is not None:
            self.e(path + ".legacy_id", "expected an integer or null")
        c = mk.get("country")
        if c is not None and (not isinstance(c, str) or not COUNTRY_RE.match(c)):
            self.e(path + ".country", "expected ISO 3166-1 alpha-2 (e.g. 'US'), got %r" % (c,))
        self.string(mk.get("headquarters"), path + ".headquarters")
        self.year(mk.get("founded"), path + ".founded", 1800, YEAR_MAX)
        self.string(mk.get("parent_group"), path + ".parent_group")
        self.url(mk.get("website_url"), path + ".website_url")
        self.enum(mk.get("status"), path + ".status", MAKE_STATUS)
        self.date(mk.get("status_date"), path + ".status_date")
        self.string(mk.get("status_details"), path + ".status_details")
        self.string(mk.get("description"), path + ".description")
        srcs = self.sources(mk.get("sources"), path + ".sources")
        if mk.get("status") in ("defunct", "acquired"):
            self.needs_status_source(srcs, path + ".sources",
                                     "make status '%s'" % mk["status"])
            if mk.get("status_date") is None:
                self.w(path + ".status_date", "defunct/acquired make has no status_date")
            if mk.get("status_details") is None:
                self.w(path + ".status_details", "defunct/acquired make has no status_details")

    def model(self, m, path, url_slugs):
        if not self.obj(m, path, MODEL_REQ, MODEL_OPT):
            return
        self.rep.counts["models"] += 1
        s = m.get("slug")
        self.slug(s, path + ".slug")
        if isinstance(s, str):
            if s in self.model_slugs:
                self.e(path + ".slug", "duplicate model slug %r (also at %s)"
                       % (s, self.model_slugs[s]))
            else:
                self.model_slugs[s] = path
        us = m.get("url_slug")
        self.slug(us, path + ".url_slug")
        if isinstance(us, str):
            if us.isdigit():
                self.e(path + ".url_slug", "url_slug %r is all digits; prefix the make" % us)
            if "-vs-" in us or us.startswith("vs-") or us.endswith("-vs"):
                self.e(path + ".url_slug", "url_slug %r must not contain 'vs'" % us)
            if us in url_slugs:
                self.e(path + ".url_slug", "duplicate url_slug %r (also at %s)"
                       % (us, url_slugs[us]))
            else:
                url_slugs[us] = path
        self.string(m.get("name"), path + ".name")
        for i, a in enumerate(self.lst(m.get("aliases"), path + ".aliases")):
            if not is_str(a):
                self.e("%s.aliases[%d]" % (path, i), "expected a non-empty string")
        self.enum(m.get("body_style"), path + ".body_style", BODY)
        self.boolean(m.get("is_commercial"), path + ".is_commercial")
        self.enum(m.get("status"), path + ".status", LIFECYCLE)
        self.url(m.get("official_url"), path + ".official_url")
        self.string(m.get("description"), path + ".description")

        mk = m.get("markets")
        if mk is not None:
            if not isinstance(mk, dict):
                self.e(path + ".markets", "expected an object keyed by market")
            else:
                for code, mv in mk.items():
                    p = "%s.markets.%s" % (path, code)
                    self.enum(code, p, MARKETS)
                    if self.obj(mv, p, MARKET_REQ, MARKET_OPT):
                        self.enum(mv.get("status"), p + ".status", LIFECYCLE)
                        self.date(mv.get("launch"), p + ".launch")
                        self.date(mv.get("end"), p + ".end")
                        self.string(mv.get("local_name"), p + ".local_name")

        for i, r in enumerate(self.lst(m.get("relations"), path + ".relations")):
            p = "%s.relations[%d]" % (path, i)
            if self.obj(r, p, RELATION_REQ, set()):
                self.enum(r.get("relation"), p + ".relation", RELATIONS)
                self.slug(r.get("model"), p + ".model")
                if isinstance(r.get("model"), str):
                    if r["model"] == s:
                        self.e(p + ".model", "model relates to itself")
                    self.relation_refs.append((p + ".model", r["model"]))

        srcs = self.sources(m.get("sources"), path + ".sources")
        if m.get("status") in ("discontinued", "cancelled"):
            self.needs_status_source(srcs, path + ".sources",
                                     "model status '%s'" % m["status"])

        gens = self.lst(m.get("generations"), path + ".generations", allow_none=False)
        if not gens:
            self.e(path + ".generations", "a model needs at least one generation")
        gen_slugs = {}
        gen_ordinals = set()
        refresh_ordinals = []
        legacy_seen = False
        for i, g in enumerate(gens):
            gp = "%s.generations[%d]" % (path, i)
            if self.generation(g, gp, gen_slugs):
                legacy_seen = legacy_seen or self._gen_has_legacy(g)
                if is_int(g.get("ordinal")):
                    if g.get("kind") == "refresh":
                        refresh_ordinals.append((gp + ".ordinal", g["ordinal"]))
                    else:
                        gen_ordinals.add(g["ordinal"])
        for p, o in refresh_ordinals:
            if o not in gen_ordinals:
                self.w(p, "refresh ordinal %d matches no 'generation' row" % o)

        # model status vs generation statuses
        gstat = {g.get("status") for g in gens if isinstance(g, dict)}
        if m.get("status") == "current" and gens and "current" not in gstat:
            self.w(path + ".status", "model is 'current' but no generation is 'current'")
        if m.get("status") in ("discontinued", "cancelled") and "current" in gstat:
            self.w(path + ".status", "model is '%s' but a generation is 'current'"
                   % m["status"])

        if (isinstance(s, str) and self.make_slug and not legacy_seen
                and not s.startswith(self.make_slug + "-")):
            self.w(path + ".slug", "new model slug %r should start with '%s-'"
                   % (s, self.make_slug))

    @staticmethod
    def _gen_has_legacy(g):
        for v in g.get("variants") or []:
            if isinstance(v, dict) and v.get("legacy_ids"):
                return True
        return False

    def generation(self, g, path, gen_slugs):
        if not self.obj(g, path, GEN_REQ, GEN_OPT):
            return False
        self.rep.counts["generations"] += 1
        s = g.get("slug")
        self.slug(s, path + ".slug", GEN_SLUG_RE,
                  "4-digit first year, optional '-suffix', e.g. '2024' or '2024-refresh'")
        if isinstance(s, str):
            if s in gen_slugs:
                self.e(path + ".slug", "duplicate generation slug %r (also at %s)"
                       % (s, gen_slugs[s]))
            else:
                gen_slugs[s] = path
        self.string(g.get("name"), path + ".name")
        self.enum(g.get("kind"), path + ".kind", GEN_KIND)
        o = g.get("ordinal")
        if o is not None and (not is_int(o) or o < 1):
            self.e(path + ".ordinal", "expected a positive integer, got %r" % (o,))
        self.string(g.get("code_name"), path + ".code_name")
        self.string(g.get("platform"), path + ".platform")
        self.year(g.get("start_year"), path + ".start_year")
        self.year(g.get("end_year"), path + ".end_year")
        self.year_order(g.get("start_year"), g.get("end_year"), path,
                        "start_year", "end_year")
        if (isinstance(s, str) and GEN_SLUG_RE.match(s) and is_int(g.get("start_year"))
                and abs(int(s[:4]) - g["start_year"]) > 1):
            self.w(path + ".slug", "slug year %s far from start_year %d"
                   % (s[:4], g["start_year"]))
        st = g.get("status")
        self.enum(st, path + ".status", LIFECYCLE)
        if st == "discontinued" and g.get("end_year") is None:
            self.w(path + ".end_year", "discontinued generation has no end_year")
        self.string(g.get("description"), path + ".description")
        for i, im in enumerate(self.lst(g.get("images"), path + ".images")):
            self.image(im, "%s.images[%d]" % (path, i))
        self.sources(g.get("sources"), path + ".sources")

        vs = self.lst(g.get("variants"), path + ".variants", allow_none=False)
        if not vs and st != "cancelled":
            self.w(path + ".variants", "generation has no variants")
        var_slugs = {}
        for i, v in enumerate(vs):
            self.variant(v, "%s.variants[%d]" % (path, i), var_slugs, st)
        return True

    def image(self, im, path):
        if not self.obj(im, path, IMG_REQ, IMG_OPT):
            return
        self.rep.counts["images"] += 1
        src = im.get("source")
        self.enum(src, path + ".source", IMG_SOURCE)
        fu = im.get("file_url")
        if src == "legacy":
            if not isinstance(fu, str) or not fu.startswith(LEGACY_IMG_PREFIX):
                self.e(path + ".file_url", "legacy image must be a path under %s"
                       % LEGACY_IMG_PREFIX)
            if im.get("verified_by_viewing") is not True:
                self.e(path + ".verified_by_viewing",
                       "legacy images may only be used after viewing (must be true)")
        else:
            self.url(fu, path + ".file_url")
            self.url(im.get("page_url"), path + ".page_url")
            if im.get("page_url") is None:
                self.e(path + ".page_url", "%s image needs page_url" % src)
            if not is_str(im.get("credit")):
                self.e(path + ".credit", "%s image needs credit" % src)
            if src == "commons" and not is_str(im.get("license")):
                self.e(path + ".license", "commons image needs license")
            if im.get("verified_by_viewing") is not True:
                self.w(path + ".verified_by_viewing",
                       "image not verified by viewing; loader should not show it")
        self.string(im.get("credit"), path + ".credit")
        self.string(im.get("license"), path + ".license")
        self.enum(im.get("view"), path + ".view", IMG_VIEW)
        self.boolean(im.get("verified_by_viewing"), path + ".verified_by_viewing")

    def variant(self, v, path, var_slugs, gen_status):
        if not self.obj(v, path, VAR_REQ, VAR_OPT):
            return
        self.rep.counts["variants"] += 1
        s = v.get("slug")
        self.slug(s, path + ".slug")
        if isinstance(s, str):
            if s in var_slugs:
                self.e(path + ".slug", "duplicate variant slug %r (also at %s)"
                       % (s, var_slugs[s]))
            else:
                var_slugs[s] = path
        self.string(v.get("name"), path + ".name")

        for i, lid in enumerate(self.lst(v.get("legacy_ids"), path + ".legacy_ids")):
            p = "%s.legacy_ids[%d]" % (path, i)
            if not is_int(lid):
                self.e(p, "expected an integer, got %r" % (lid,))
            elif lid in self.claims:
                self.e(p, "legacy id %d already claimed at %s" % (lid, self.claims[lid]))
            else:
                self.claims[lid] = p

        st = v.get("status")
        self.enum(st, path + ".status", LIFECYCLE)
        if st == "current" and gen_status in ("discontinued", "cancelled"):
            self.w(path + ".status", "variant is 'current' under a '%s' generation"
                   % gen_status)
        self.year(v.get("year_from"), path + ".year_from")
        self.year(v.get("year_to"), path + ".year_to")
        self.year_order(v.get("year_from"), v.get("year_to"), path, "year_from", "year_to")
        self.enum(v.get("drivetrain"), path + ".drivetrain", DRIVETRAIN)
        self.enum(v.get("body_type"), path + ".body_type", BODY)
        if v.get("seats") is not None and not is_int(v["seats"]):
            self.e(path + ".seats", "expected an integer, got %r" % (v["seats"],))
        self.enum(v.get("battery_basis"), path + ".battery_basis", BATTERY_BASIS)
        if v.get("battery_basis") is not None and v.get("battery_kwh") is None:
            self.w(path + ".battery_basis", "battery_basis set without battery_kwh")
        for field, lo, hi in VARIANT_BOUNDS:
            if self.number(v.get(field), "%s.%s" % (path, field)):
                self.bounds(v[field], "%s.%s" % (path, field), lo, hi, field)

        self.sources(v.get("sources"), path + ".sources", nonempty=True)

        seen = {}
        for i, o in enumerate(self.lst(v.get("offerings"), path + ".offerings")):
            p = "%s.offerings[%d]" % (path, i)
            self.offering(o, p)
            if isinstance(o, dict):
                key = (o.get("market"), o.get("model_year"))
                if key in seen:
                    self.e(p, "duplicate offering for market %s model_year %s (also at %s)"
                           % (key[0], key[1], seen[key]))
                else:
                    seen[key] = p

    def offering(self, o, path):
        if not self.obj(o, path, OFF_REQ, OFF_OPT):
            return
        self.rep.counts["offerings"] += 1
        self.enum(o.get("market"), path + ".market", MARKETS)
        self.year(o.get("model_year"), path + ".model_year")

        rng, unit, cyc = o.get("range"), o.get("range_unit"), o.get("range_cycle")
        self.enum(unit, path + ".range_unit", {"mi", "km"})
        self.enum(cyc, path + ".range_cycle", set(RANGE_CYCLE_UNIT))
        if self.number(rng, path + ".range"):
            if unit is None or cyc is None:
                self.e(path + ".range", "range needs range_unit and range_cycle")
            if cyc in RANGE_CYCLE_UNIT and unit in ("mi", "km") \
                    and RANGE_CYCLE_UNIT[cyc] != unit:
                self.e(path + ".range_unit", "%s range must be in %s, got %s"
                       % (cyc, RANGE_CYCLE_UNIT[cyc], unit))
            if unit == "mi":
                lo, hi = (30, 800)
            else:
                lo, hi = (50, 1300)
            self.bounds(rng, path + ".range", lo, hi, "%s range (%s)" % (cyc, unit))
        elif unit is not None or cyc is not None:
            self.w(path, "range_unit/range_cycle set without range")

        has_price = False
        for f in ("price", "launch_price"):
            if self.number(o.get(f), "%s.%s" % (path, f)):
                has_price = True
        cur, basis = o.get("currency"), o.get("price_basis")
        if cur is not None and (not isinstance(cur, str) or not CURRENCY_RE.match(cur)):
            self.e(path + ".currency", "expected ISO 4217 code (e.g. 'USD'), got %r" % (cur,))
        self.enum(basis, path + ".price_basis", PRICE_BASIS)
        if has_price and (cur is None or basis is None):
            self.e(path, "price/launch_price needs currency and price_basis")
        if o.get("market") == "US" and has_price and cur not in (None, "USD"):
            self.w(path + ".currency", "US offering priced in %s" % cur)
        self.enum(o.get("connector"), path + ".connector", CONNECTOR)
        self.boolean(o.get("is_estimate"), path + ".is_estimate")


# --------------------------------------------------------------- driver ----

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


def load_json(path, rep):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), True
    except OSError as ex:
        rep.err(path, "$", "cannot read file: %s" % ex)
    except json.JSONDecodeError as ex:
        rep.err(path, "$", "invalid JSON at line %d col %d: %s"
                % (ex.lineno, ex.colno, ex.msg))
    return None, False


def check_legacy(legacy_paths, checks, rep):
    """Every legacy car id must be claimed exactly once across all seed files."""
    legacy_ids = {}      # car id -> legacy file
    legacy_makes = set()
    for lp in legacy_paths:
        doc, ok = load_json(lp, rep)
        if not ok:
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("cars"), list):
            rep.err(lp, "$", "legacy file must be an object with a 'cars' array")
            continue
        mk = doc.get("make") or {}
        if is_int(mk.get("id")):
            legacy_makes.add(mk["id"])
        for i, car in enumerate(doc["cars"]):
            if isinstance(car, dict) and is_int(car.get("id")):
                legacy_ids[car["id"]] = lp
            else:
                rep.err(lp, "$.cars[%d]" % i, "legacy car without integer id")

    claimed = {}  # id -> list of (file, path)
    for fc in checks:
        for lid, p in fc.claims.items():
            claimed.setdefault(lid, []).append((fc.f, p))

    for lid in sorted(legacy_ids):
        where = claimed.get(lid, [])
        if not where:
            rep.err(legacy_ids[lid], "$.cars[id=%d]" % lid,
                    "legacy car %d is not claimed by any variant" % lid)
    for lid, where in sorted(claimed.items()):
        if lid not in legacy_ids:
            for f, p in where:
                rep.warn(f, p, "legacy id %d not found in the given legacy files" % lid)
    for fc in checks:
        if fc.make_legacy_id is not None and legacy_makes \
                and fc.make_legacy_id not in legacy_makes:
            rep.warn(fc.f, "$.make.legacy_id",
                     "make legacy_id %d not found in the given legacy files"
                     % fc.make_legacy_id)
    return {"legacy_cars": len(legacy_ids),
            "legacy_claimed": len([i for i in legacy_ids if i in claimed])}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate catalog seed JSON files.")
    ap.add_argument("paths", nargs="+", help="seed files or directories")
    ap.add_argument("--legacy", action="append", default=[],
                    help="legacy/{make}.json; every car id in it must be claimed once")
    ap.add_argument("--json", action="store_true", help="print a JSON summary")
    args = ap.parse_args(argv)

    rep = Report()
    files = expand(args.paths)
    if not files:
        rep.err("-", "$", "no seed files found in %s" % ", ".join(args.paths))

    checks = []
    for f in files:
        doc, ok = load_json(f, rep)
        rep.counts["files"] += 1
        if not ok:
            continue
        fc = FileCheck(rep, f)
        fc.run(doc)
        checks.append(fc)

    # cross-file: model slugs, make slugs, legacy claims, relation targets
    all_models, make_slugs, all_claims = {}, {}, {}
    for fc in checks:
        if fc.make_slug:
            if fc.make_slug in make_slugs:
                rep.err(fc.f, "$.make.slug", "make slug %r also in %s"
                        % (fc.make_slug, make_slugs[fc.make_slug]))
            make_slugs.setdefault(fc.make_slug, fc.f)
        for s, p in fc.model_slugs.items():
            if s in all_models:
                rep.err(fc.f, p + ".slug", "model slug %r also in %s" % (s, all_models[s]))
            all_models.setdefault(s, fc.f)
        for lid, p in fc.claims.items():
            if lid in all_claims:
                rep.err(fc.f, p, "legacy id %d also claimed in %s" % (lid, all_claims[lid]))
            all_claims.setdefault(lid, fc.f)
    for fc in checks:
        for p, target in fc.relation_refs:
            if target not in all_models:
                rep.warn(fc.f, p, "related model %r not in the validated files" % target)

    legacy_summary = check_legacy(args.legacy, checks, rep) if args.legacy else None

    if args.json:
        out = dict(rep.counts)
        out["errors"] = len(rep.errors)
        out["warnings"] = len(rep.warnings)
        if legacy_summary:
            out.update(legacy_summary)
        out["ok"] = not rep.errors
        out["error_list"] = rep.errors
        out["warning_list"] = rep.warnings
        print(json.dumps(out, indent=2))
    else:
        for x in rep.errors:
            print("ERROR %s %s: %s" % (x["file"], x["path"], x["message"]))
        for x in rep.warnings:
            print("WARN  %s %s: %s" % (x["file"], x["path"], x["message"]))
        c = rep.counts
        line = ("%d file(s): %d models, %d generations, %d variants, %d offerings, "
                "%d images; %d error(s), %d warning(s)"
                % (c["files"], c["models"], c["generations"], c["variants"],
                   c["offerings"], c["images"], len(rep.errors), len(rep.warnings)))
        if legacy_summary:
            line += "; legacy %d/%d claimed" % (legacy_summary["legacy_claimed"],
                                                legacy_summary["legacy_cars"])
        print(line)
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
