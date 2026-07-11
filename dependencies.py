"""Shared dependencies used across all routers."""

import os
from typing import Annotated, Optional, Dict

from fastapi import Depends, Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
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

# --- Legacy API key auth (kept for backward compatibility during migration) ---

API_KEY = os.getenv("API_SECRET_KEY", "no_key")
API_KEY_NAME = os.getenv("API_SECRET_KEY_NAME", "no_key_name")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    """Legacy API key check for read endpoints. Will be removed once public GETs go open."""
    if api_key_header == API_KEY:
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )


async def get_admin_api_key(
    api_key_header: str = Security(api_key_header),
    admin_key: str = Security(admin_key_header),
):
    """Legacy admin key check. Will be replaced by JWT-based admin auth."""
    if api_key_header != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    if not ADMIN_SECRET_KEY or admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key",
        )
    return admin_key


# --- Helper functions ---

def calculate_average_rating(ratings: Optional[Dict[str, float]]) -> float:
    if ratings:
        total = sum(ratings.values())
        count = len(ratings)
        return round((total / count), 2) if count else 0
    return 0
