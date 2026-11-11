"""Slug rules for the catalog (design doc section 5.1).

Pure functions; no database access. Slugs are lowercase ASCII [a-z0-9-] with
accents transliterated, and never change once published (a change adds a
url_redirects row instead).
"""
import re
import unicodedata
from typing import Iterable, Optional

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GENERATION_SLUG_RE = re.compile(r"^[0-9]{4}(?:-[a-z0-9]+)*$")


def slugify(text: Optional[str]) -> str:
    """'Citroën ë-C4' -> 'citroen-e-c4'; 'ID.4' -> 'id-4'; '' -> ''."""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def model_url_slug(make_slug: str, model_name: str) -> str:
    """Model URL slug: slugify(name); all digits gets the make prefixed ('polestar-2')."""
    s = slugify(model_name)
    if s.isdigit():
        s = "%s-%s" % (make_slug, s)
    return s


def is_valid_model_url_slug(s: Optional[str]) -> bool:
    return bool(
        isinstance(s, str)
        and SLUG_RE.match(s)
        and not s.isdigit()
        and "-vs-" not in s
        and not s.startswith("vs-")
        and not s.endswith("-vs")
    )


def model_api_slug(make_slug: str, url_slug: str, legacy_slug: Optional[str] = None) -> str:
    """models.slug: existing models keep the legacy make_model_slug; new ones '{make}-{url_slug}'."""
    return legacy_slug or "%s-%s" % (make_slug, url_slug)


def generation_slug(start_year: int, taken: Iterable[str] = (), suffix: Optional[str] = None) -> str:
    """First model year; a second generation starting the same year gets '-{suffix}' (default 'refresh')."""
    base = "%04d" % int(start_year)
    taken = set(taken)
    if base not in taken:
        return base
    cand = "%s-%s" % (base, slugify(suffix) or "refresh")
    n = 2
    while cand in taken:
        cand = "%s-gen%d" % (base, n)
        n += 1
    return cand


def legacy_make_path_slug(name: Optional[str]) -> str:
    """Mirror of the frontend's makeNameToSlug and routers/seo.make_name_to_slug:
    lowercase, whitespace -> '-', drop everything but [a-z0-9-] ('Citroën' -> 'citron')."""
    s = re.sub(r"\s+", "-", (name or "").lower())
    return re.sub(r"[^a-z0-9-]", "", s)


def variant_full_slug(make_slug: str, url_slug: str, gen_slug: str, variant_slug: str,
                      taken: Iterable[str] = ()) -> str:
    """Legacy cars.full_slug for a catalog-created variant row; unique against `taken`."""
    base = "-".join(p for p in (make_slug, url_slug, gen_slug, variant_slug) if p)
    taken = set(taken)
    cand, n = base, 2
    while cand in taken:
        cand = "%s-%d" % (base, n)
        n += 1
    return cand
