"""SEO endpoints.

/sitemap.xml is generated from the DB and proxied through the frontend domain
(www.evlineup.org/sitemap.xml -> this endpoint) via a Vercel rewrite, so it
always reflects the live catalog without a rebuild.
"""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

import models.orm_models as models
from dependencies import db_dependency

router = APIRouter(tags=["seo"])

CANONICAL_HOST = "https://www.evlineup.org"

STATIC_PATHS = ["/", "/about", "/people", "/marketplace", "/advertise", "/privacy", "/terms"]

# Programmatic SEO pages. BEST_PATHS is only used by the legacy sitemap below (before the catalog
# migration); the catalog sitemap lists the indexable lists of services/catalog_lists.py.
BEST_PATHS = [
    "/best/evs-under-40k",
    "/best/longest-range-evs",
    "/best/fastest-evs",
    "/best/cheapest-evs",
    "/best/3-row-evs",
]

# Pinned comparison pairs: THE single list (services/catalog_compare.py selects them first and they are
# always indexable while both models exist and are not cancelled). Canonical form: the two catalog
# model slugs in alphabetical order, so every link and sitemap entry is the canonical URL.
COMPARE_PAIRS = [
    "bmw-i4-vs-tesla-model-3",
    "hyundai-ioniq-5-vs-kia-ev6",
    "ford-mustang-mach-e-vs-tesla-model-y",
    "rivian-r1s-vs-tesla-model-x",
    "hyundai-ioniq-6-vs-tesla-model-3",
    "ford-f150-lightning-vs-tesla-cybertruck",
    "chevrolet-equinox-ev-vs-tesla-model-y",
    "kia-ev9-vs-rivian-r1s",
    "hyundai-ioniq-5-vs-tesla-model-y",
    "ford-f150-lightning-vs-rivian-r1t",
]


def make_name_to_slug(name: str) -> str:
    """Mirror of frontend makeNameToSlug (src/utils/makeSlug.ts):
    lowercase, whitespace -> '-', strip everything but [a-z0-9-]."""
    slug = re.sub(r"\s+", "-", (name or "").lower())
    return re.sub(r"[^a-z0-9-]", "", slug)


def _lastmod(dt: Optional[datetime]) -> str:
    return (dt or datetime.utcnow()).strftime("%Y-%m-%d")


def _url(loc: str, lastmod: str, priority: str) -> str:
    return (
        f"  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <priority>{priority}</priority>\n"
        f"  </url>\n"
    )


@router.get("/sitemap.xml")
async def sitemap(db: db_dependency):
    # Once the catalog is migrated and loaded, the catalog sitemap (new /make/... URLs)
    # replaces this one. Until then, and on any catalog error, serve the legacy sitemap.
    try:
        from fastapi import HTTPException
        from sqlalchemy import text
        from routers import catalog

        if db.execute(text("SELECT 1 FROM generations LIMIT 1")).first():
            return await catalog.catalog_sitemap(db=db)
    except (SQLAlchemyError, HTTPException):
        db.rollback()

    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n',
    ]

    for path in STATIC_PATHS:
        priority = "1.0" if path == "/" else "0.6"
        parts.append(_url(f"{CANONICAL_HOST}{path}", today, priority))

    for path in BEST_PATHS:
        parts.append(_url(f"{CANONICAL_HOST}{path}", today, "0.8"))

    for pair in COMPARE_PAIRS:
        parts.append(_url(f"{CANONICAL_HOST}/compare/{pair}", today, "0.8"))

    # Model pages — only slugs with a representative car (others 404)
    model_rows = (
        db.query(models.Car.make_model_slug, func.max(models.Car.updated_at))
        .filter(models.Car.is_model_rep == True)  # noqa: E712
        .group_by(models.Car.make_model_slug)
        .all()
    )
    for slug, updated in sorted(model_rows):
        if not slug:
            continue
        parts.append(
            _url(f"{CANONICAL_HOST}/model_detail/{slug}", _lastmod(updated), "0.8")
        )

    # Manufacturer pages
    make_rows = db.query(models.Make.name, models.Make.updated_at).all()
    for name, updated in sorted(make_rows):
        slug = make_name_to_slug(name)
        if not slug:
            continue
        parts.append(
            _url(f"{CANONICAL_HOST}/manufacturer/{slug}", _lastmod(updated), "0.7")
        )

    parts.append("</urlset>\n")
    return Response(
        content="".join(parts),
        media_type="application/xml",
        headers={
            # CDN-cache for an hour; serve stale while refreshing
            "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
        },
    )
