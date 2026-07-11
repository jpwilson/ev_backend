"""Newsletter endpoints — email capture for the EV Radar digest."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

import models.orm_models as models
from auth import get_admin_access
from dependencies import db_dependency

router = APIRouter(tags=["newsletter"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SubscribeRequest(BaseModel):
    email: str
    # Honeypot: real users never fill this; bots do. Field name looks legit.
    website: str = ""


@router.post("/newsletter/subscribe")
async def subscribe(req: SubscribeRequest, db: db_dependency):
    # Honeypot tripped — pretend success, store nothing
    if req.website:
        return {"status": "subscribed"}

    email = req.email.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 320:
        raise HTTPException(status_code=422, detail="Please enter a valid email address")

    existing = (
        db.query(models.NewsletterSubscriber)
        .filter(func.lower(models.NewsletterSubscriber.email) == email)
        .first()
    )
    if existing:
        if existing.unsubscribed_at is not None:
            existing.unsubscribed_at = None  # resubscribe
            db.commit()
        return {"status": "subscribed"}

    db.add(models.NewsletterSubscriber(email=email))
    db.commit()
    return {"status": "subscribed"}


@router.get("/admin/newsletter")
async def newsletter_stats(db: db_dependency, admin: dict = Depends(get_admin_access)):
    total = db.query(func.count(models.NewsletterSubscriber.id)).scalar()
    active = (
        db.query(func.count(models.NewsletterSubscriber.id))
        .filter(models.NewsletterSubscriber.unsubscribed_at.is_(None))
        .scalar()
    )
    latest = (
        db.query(models.NewsletterSubscriber)
        .order_by(models.NewsletterSubscriber.id.desc())
        .limit(10)
        .all()
    )
    return {
        "total": total,
        "active": active,
        "latest": [
            {"email": s.email, "subscribed_at": str(s.subscribed_at)} for s in latest
        ],
    }
