"""Admin endpoints."""

from fastapi import APIRouter, Depends

from dependencies import get_admin_api_key

router = APIRouter(tags=["admin"])


@router.get("/admin/verify")
async def verify_admin_key(admin_key: str = Depends(get_admin_api_key)):
    return {"status": "ok", "message": "Admin key verified"}
