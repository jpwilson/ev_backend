"""/catalog/* read API: makes -> models -> generations -> variants -> offerings.

Public GETs. Reads only the catalog Core tables (services/catalog_tables.py), never
the legacy ORM, so this router can ship before the migration: until
catalog_02_hierarchy is applied every /catalog/* route answers 503 JSON and the
legacy routes are unaffected. Response shapes: docs/catalog-api.md.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.exc import OperationalError, ProgrammingError

import services.catalog_service as svc
from dependencies import db_dependency
from routers.seo import CANONICAL_HOST, COMPARE_PAIRS, STATIC_PATHS

router = APIRouter(prefix="/catalog", tags=["catalog"])

# Same CDN policies as the legacy public GETs (routers/cars.py, makes.py, seo.py)
CACHE_LIST = "public, s-maxage=300, stale-while-revalidate=3600"
CACHE_DETAIL = "public, s-maxage=600, stale-while-revalidate=3600"
CACHE_MAKES = "public, s-maxage=3600, stale-while-revalidate=86400"
NOT_READY = "Catalog tables are not available yet (migration catalog_02_hierarchy has not been applied)."
NO_STORE = {"Cache-Control": "no-store", "Retry-After": "300"}


def _conn(db):
    """Connection for Core queries, or 503 when the catalog tables do not exist."""
    try:
        conn = db.connection()
        if svc.tables_ready(conn):
            return conn
    except (ProgrammingError, OperationalError):
        db.rollback()
    raise HTTPException(status_code=503, detail=NOT_READY, headers=NO_STORE)


def _guard(fn):
    """Turn a missing column/table discovered mid-request into the same 503."""
    import functools
    import inspect

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (ProgrammingError, OperationalError) as e:
            if "does not exist" in str(e):
                raise HTTPException(status_code=503, detail=NOT_READY, headers=NO_STORE)
            raise
    wrapper.__signature__ = inspect.signature(fn)
    return wrapper


def _csv(v: Optional[str]):
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


@router.get("/meta")
@_guard
async def catalog_meta(db: db_dependency, response: Response):
    data = svc.meta(_conn(db))
    response.headers["Cache-Control"] = CACHE_LIST
    return data


@router.get("/makes")
@_guard
async def catalog_makes(db: db_dependency, response: Response,
                        status: Optional[str] = Query(None, description="display status filter, comma separated")):
    cat = svc.Catalog(_conn(db))
    wanted = set(_csv(status))
    makes = [cat.make_summary(m) for m in cat.makes.values()]
    if wanted:
        makes = [m for m in makes if m["display_status"] in wanted]
    makes.sort(key=lambda m: (m["name"] or "").lower())
    response.headers["Cache-Control"] = CACHE_MAKES
    return {"count": len(makes), "makes": makes}


@router.get("/makes/{slug}")
@_guard
async def catalog_make(slug: str, db: db_dependency, response: Response,
                       market: Optional[str] = Query(None, description="headline market for cards, e.g. US")):
    cat = svc.Catalog(_conn(db), make_slug=slug.lower())
    make = next(iter(cat.makes.values()), None)
    if make is None:
        raise HTTPException(status_code=404, detail="Make not found")
    groups = {s: [] for s in svc.LIFECYCLE}
    for m in make["_models"]:
        groups.setdefault(m["_status"], []).append(cat.model_card(m, market))
    for cards in groups.values():
        cards.sort(key=lambda c: (-(c["years"]["start"] or 0), c["name"]))
    response.headers["Cache-Control"] = CACHE_DETAIL
    return {"make": cat.make_full(make), "models": groups}


@router.get("/models")
@_guard
async def catalog_models(
    db: db_dependency, response: Response,
    market: Optional[str] = Query(None, description="US, CA, EU, UK, CN, JP, KR, IN, AU"),
    status: Optional[str] = Query(None, description="effective status, comma separated"),
    make: Optional[str] = Query(None, description="make slug(s), comma separated"),
    body_style: Optional[str] = Query(None, description="comma separated"),
    q: Optional[str] = Query(None, description="text search over make, model, aliases"),
    commercial: Optional[bool] = Query(None, description="true/false; omitted = both"),
    limit: Optional[int] = Query(None, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    cat = svc.Catalog(_conn(db))
    market = market.upper() if market else None
    statuses, makes, bodies = set(_csv(status)), set(_csv(make)), set(_csv(body_style))
    terms = (q or "").lower().split()
    out = []
    for m in cat.models.values():
        mk = cat.makes[m["make_id"]]
        if makes and mk["slug"] not in makes:
            continue
        if bodies and m["body_style"] not in bodies:
            continue
        if commercial is not None and bool(m["is_commercial"]) != commercial:
            continue
        if market:
            mm = cat.markets[m["id"]].get(market)
            if mm is None:
                continue
            eff = mm["_status"]
        else:
            eff = m["_status"]
        if statuses and eff not in statuses:
            continue
        if terms:
            hay = " ".join([mk["catalog_name"] or "", mk["slug"], m["name"], m["slug"]] +
                           list(m["aliases"] or [])).lower()
            if not all(t in hay for t in terms):
                continue
        out.append(cat.model_card(m, market))
    out.sort(key=lambda c: ((c["make"]["name"] or "").lower(), (c["name"] or "").lower()))
    total = len(out)
    out = out[offset: offset + limit if limit else None]
    response.headers["Cache-Control"] = CACHE_LIST
    return {"count": total, "offset": offset, "market": market, "models": out}


@router.get("/models/{make}/{model}")
@_guard
async def catalog_model(make: str, model: str, db: db_dependency, response: Response):
    cat = svc.Catalog(_conn(db), model_key=(make.lower(), model.lower()))
    m = next(iter(cat.models.values()), None)
    if m is None:
        raise HTTPException(status_code=404, detail="Model not found")
    response.headers["Cache-Control"] = CACHE_DETAIL
    return cat.model_tree(m)


@router.get("/variants/{make}/{model}/{generation}/{variant}")
@_guard
async def catalog_variant(make: str, model: str, generation: str, variant: str,
                          db: db_dependency, response: Response):
    cat = svc.Catalog(_conn(db), model_key=(make.lower(), model.lower()))
    m = next(iter(cat.models.values()), None)
    gen = next((g for g in cat.gens_by_model[m["id"]] if g["slug"] == generation.lower()), None) if m else None
    v = next((x for x in cat.variants_by_gen[gen["id"]] if x["variant_slug"] == variant.lower()), None) if gen else None
    if v is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    mk = cat.makes[m["make_id"]]
    siblings = sorted(cat.variants_by_gen[gen["id"]], key=svc._variant_order)
    gens = cat.gens_newest_first(m["id"])
    response.headers["Cache-Control"] = CACHE_DETAIL
    return {
        "make": cat.make_full(mk),
        "model": {"slug": m["slug"], "name": m["name"], "path": cat.model_path(m), "status": m["_status"],
                  "own_status": m["status"], "body_style": m["body_style"], "is_commercial": m["is_commercial"],
                  "official_url": m["official_url"], "years": cat.years(m)},
        "generation": cat.gen_obj(gen, with_variants=False),
        "variant": cat.variant_obj(v),
        "siblings": [dict(cat.variant_mini(x), status=x["_status"]) for x in siblings if x["id"] != v["id"]],
        "generations": [{"slug": g["slug"], "name": g["name"], "path": cat.gen_path(g), "status": g["_status"],
                         "start_year": g["start_year"], "end_year": g["end_year"]} for g in gens],
    }


@router.get("/resolve")
@_guard
async def catalog_resolve(db: db_dependency, response: Response,
                          kind: str = Query(..., description="model | make | variant"),
                          key: str = Query(..., description="legacy slug or car id")):
    if kind not in ("model", "make", "variant"):
        raise HTTPException(status_code=400, detail="kind must be model, make or variant")
    hit = svc.resolve(_conn(db), kind, key)
    if hit is None:
        raise HTTPException(status_code=404, detail="No catalog page for this %s" % kind)
    response.headers["Cache-Control"] = CACHE_DETAIL
    return hit


@router.get("/best/{key}")
@_guard
async def catalog_best(key: str, db: db_dependency, response: Response,
                       limit: Optional[int] = Query(None, ge=1, le=100)):
    data = svc.best(_conn(db), key, limit)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown best-list key; one of: %s" % ", ".join(svc.BEST))
    response.headers["Cache-Control"] = CACHE_LIST
    return data


def _url(loc: str, lastmod: Optional[datetime], priority: str) -> str:
    lm = "    <lastmod>%s</lastmod>\n" % lastmod.strftime("%Y-%m-%d") if lastmod else ""
    return "  <url>\n    <loc>%s</loc>\n%s    <priority>%s</priority>\n  </url>\n" % (loc, lm, priority)


@router.get("/sitemap.xml")
@_guard
async def catalog_sitemap(db: db_dependency):
    entries, model_slugs = svc.sitemap_entries(_conn(db))
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n']
    for path in STATIC_PATHS:
        if path == "/marketplace":  # placeholder page; design 9: only pages that exist
            continue
        parts.append(_url(CANONICAL_HOST + path, None, "1.0" if path == "/" else "0.6"))
    for key in svc.BEST:
        parts.append(_url("%s/best/%s" % (CANONICAL_HOST, key), None, "0.8"))
    seen = set()
    for pair in COMPARE_PAIRS:
        a, _, b = pair.partition("-vs-")
        if a in model_slugs and b in model_slugs:
            canon = "-vs-".join(sorted((a, b)))
            if canon not in seen:
                seen.add(canon)
                parts.append(_url("%s/compare/%s" % (CANONICAL_HOST, canon), None, "0.8"))
    for path, lastmod, prio in entries:
        parts.append(_url(CANONICAL_HOST + path, lastmod, prio))
    parts.append("</urlset>\n")
    return Response(content="".join(parts), media_type="application/xml",
                    headers={"Cache-Control": CACHE_MAKES})
