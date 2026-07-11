"""JWT-based authentication using Supabase Auth tokens.

Access control model:
- FastAPI dependencies are the PRIMARY access control gate.
- Supabase RLS is SECONDARY defense-in-depth (only applies to supabase-js calls, not SQLAlchemy).
- Admin role source of truth: auth.users.raw_app_meta_data.role (minted into JWT).
"""

import os
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader

import jwt

from dotenv import load_dotenv

load_dotenv()

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# Legacy admin key (kept for backward compatibility during migration)
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

bearer_scheme = HTTPBearer(auto_error=False)


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase JWT and return the payload."""
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT secret not configured",
        )
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Extract and verify the current user from the Authorization header. Required."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return verify_supabase_token(credentials.credentials)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Optionally extract user — returns None if no token provided."""
    if not credentials:
        return None
    try:
        return verify_supabase_token(credentials.credentials)
    except HTTPException:
        return None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require the user to have admin role in their JWT app_metadata."""
    app_metadata = user.get("app_metadata", {})
    role = app_metadata.get("role")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def get_admin_access(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    admin_key: str = Security(admin_key_header),
) -> dict:
    """Accept either JWT with admin role OR legacy X-Admin-Key header.

    This allows both auth systems to work during the migration period.
    """
    # Try JWT first
    if credentials:
        user = verify_supabase_token(credentials.credentials)
        app_metadata = user.get("app_metadata", {})
        if app_metadata.get("role") == "admin":
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    # Fall back to legacy admin key
    if ADMIN_SECRET_KEY and admin_key == ADMIN_SECRET_KEY:
        return {"sub": "legacy-admin", "role": "admin"}

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not authorized — provide a valid JWT with admin role or X-Admin-Key",
    )
