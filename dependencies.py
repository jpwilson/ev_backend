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

def calculate_average_rating(ratings: Optional[Dict[str, float]]) -> float:
    if ratings:
        total = sum(ratings.values())
        count = len(ratings)
        return round((total / count), 2) if count else 0
    return 0
