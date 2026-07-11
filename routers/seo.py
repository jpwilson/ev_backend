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

import models.orm_models as models
from dependencies import db_dependency

router = APIRouter(tags=["seo"])

CANONICAL_HOST = "https://www.evlineup.org"

STATIC_PATHS = ["/", "/about", "/people", "/marketplace"]


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
    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n',
    ]

    for path in STATIC_PATHS:
        priority = "1.0" if path == "/" else "0.6"
        parts.append(_url(f"{CANONICAL_HOST}{path}", today, priority))

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
