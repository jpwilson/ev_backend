"""Admin endpoints."""

from fastapi import APIRouter, Depends

from auth import get_admin_access

router = APIRouter(tags=["admin"])


@router.get("/admin/verify")
async def verify_admin_key(admin: dict = Depends(get_admin_access)):
    return {"status": "ok", "message": "Admin key verified"}
