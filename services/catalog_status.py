"""Effective lifecycle status, computed once for every page and API (design 2.5).

Stored values:
  make:                                  active | pre-production | defunct | acquired
  model / generation / variant / market: upcoming | current | discontinued | cancelled
                                         (variant NULL = inherit its generation)

Coercion runs make -> model -> generation -> variant (and model -> model x market):
  - brand defunct (defunct or acquired) or parent discontinued:
        current -> discontinued, upcoming -> cancelled
  - parent cancelled: child -> cancelled
  - parent upcoming with a current child: kept, reported as a data warning
The model's own stored value stays visible next to the effective one.
"""
from typing import Iterable, List, Optional, Tuple

LIFECYCLE = ("upcoming", "current", "discontinued", "cancelled")
MAKE_STATUSES = ("active", "pre-production", "defunct", "acquired")
DEFUNCT_MAKE_STATUSES = ("defunct", "acquired")


def brand_status(make_status: Optional[str]) -> Optional[str]:
    """'defunct' for defunct or acquired brands, else the stored make status."""
    if make_status in DEFUNCT_MAKE_STATUSES:
        return "defunct"
    return make_status


def is_brand_defunct(make_status: Optional[str]) -> bool:
    return make_status in DEFUNCT_MAKE_STATUSES


def coerce(own: Optional[str], parent: Optional[str] = None, brand_defunct: bool = False) -> Optional[str]:
    """Effective status of a child given its own value and its parent's effective value."""
    if own is None:
        return parent
    if parent == "cancelled":
        return "cancelled"
    if brand_defunct or parent == "discontinued":
        if own == "current":
            return "discontinued"
        if own == "upcoming":
            return "cancelled"
    return own


def consistency_warning(own: Optional[str], parent: Optional[str]) -> Optional[str]:
    if parent == "upcoming" and own == "current":
        return "current under an upcoming parent"
    return None


def model_status(model_own: Optional[str], make_status: Optional[str]) -> Optional[str]:
    return coerce(model_own, None, is_brand_defunct(make_status))


def generation_status(gen_own: Optional[str], model_effective: Optional[str], make_status: Optional[str]) -> Optional[str]:
    return coerce(gen_own, model_effective, is_brand_defunct(make_status))


def variant_status(variant_own: Optional[str], gen_own: Optional[str], gen_effective: Optional[str],
                   make_status: Optional[str]) -> Optional[str]:
    """A NULL variant status inherits the generation's (already effective) status."""
    if variant_own is None:
        return gen_effective
    return coerce(variant_own, gen_effective, is_brand_defunct(make_status))


def market_status(market_own: Optional[str], model_effective: Optional[str], make_status: Optional[str]) -> Optional[str]:
    return coerce(market_own, model_effective, is_brand_defunct(make_status))


def make_display_status(make_status: Optional[str], model_effective: Iterable[Optional[str]]) -> Optional[str]:
    """Label for a make: defunct, else from its models (current > upcoming > discontinued)."""
    if is_brand_defunct(make_status):
        return "defunct"
    statuses = [s for s in model_effective if s]
    if not statuses:
        if make_status == "pre-production":
            return "upcoming"
        # An active brand with no electric model listed sells no EV: no label.
        return None
    for s in ("current", "upcoming"):
        if s in statuses:
            return s
    return "discontinued"


def generation_sort_key(gen: dict) -> Tuple:
    """Newest first when sorted descending: start_year, then ordinal, then slug."""
    return (gen.get("start_year") or 0, gen.get("ordinal") or 0, gen.get("slug") or "")


def default_generation(gens: List[dict], status_key: str = "status") -> Optional[dict]:
    """Newest current generation; else newest not cancelled; else newest (design 6.1)."""
    if not gens:
        return None
    ordered = sorted(gens, key=generation_sort_key, reverse=True)
    for g in ordered:
        if g.get(status_key) == "current":
            return g
    for g in ordered:
        if g.get(status_key) != "cancelled":
            return g
    return ordered[0]
