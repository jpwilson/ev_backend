"""Shared dependencies used across all routers.

Access control lives in auth.py:
- Public GETs are open (the catalog is the product; the old read key shipped
  inside the JS bundle and provided no security).
- Writes and admin reads require get_admin_access (JWT admin role or X-Admin-Key).
"""

from typing import Annotated, Optional, Dict

from fastapi import Depends
from sqlalchemy.orm import Session

from database import SessionLocal

from dotenv import load_dotenv

load_dotenv()

# --- Database dependency ---

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]


# --- Helper functions ---

def calculate_average_rating(ratings: Optional[Dict[str, float]]) -> Optional[float]:
    """Average review scores normalized to a /10 scale.

    Source data mixes scales (Edmunds/US News use /10: 7.1-9.4; Car and
    Driver/Consumer Reports entries were stored as /5: 4.0-4.7) and contains
    0.0 placeholders. Values <= 5 are treated as /5 and doubled; <= 0 entries
    are dropped. Returns None (not 0) when there's no usable data so the UI
    can hide the badge instead of showing a broken-looking red zero.
    """
    if not ratings:
        return None
    normalized = []
    for value in ratings.values():
        if value is None or value <= 0:
            continue
        normalized.append(min(value * 2, 10.0) if value <= 5 else min(value, 10.0))
    if not normalized:
        return None
    return round(sum(normalized) / len(normalized), 1)
