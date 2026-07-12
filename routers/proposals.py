"""Change-proposal pipeline: crawlers propose, the Data Inbox approves.

Iron rule: fetchers never write cars/makes/models directly — they POST
proposals here; approval (human, or auto_apply for proven-safe classes
later) is what mutates the catalog, stamping provenance as it goes.

All endpoints degrade gracefully until migrations 002+003 are applied:
a clear 503 instead of a stack trace.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError, ProgrammingError

import models.orm_models as models
from models.pipeline_models import ChangeProposal, CrawlRun, VehicleModel
from auth import get_admin_access
from dependencies import db_dependency

router = APIRouter(tags=["proposals"])

MIGRATION_HINT = (
    "Data pipeline tables not ready — run migrations/002 and 003 in the "
    "Supabase SQL Editor."
)

# Whitelist of crawler-writable fields per entity. Guards both proposal
# creation and apply-time, so a bad fetcher can't write arbitrary columns.
ALLOWED_FIELDS = {
    "car": {
        "epa_range", "current_price", "acceleration_0_60", "top_speed",
        "power", "torque", "battery_capacity", "battery_max_charging_speed",
        "availability_desc", "production_availability", "model_webpage",
        "image_url", "number_of_full_adult_seats", "vehicle_class",
    },
    "make": {
        "status", "status_details", "website_url", "num_ev_models",
        "headquarters", "country", "update_cadence",
    },
    "model": {
        "status", "body_style", "description", "official_url",
        "update_cadence", "announced_date", "launch_date", "discontinued_date",
    },
}

ENTITY_ORM = {"car": models.Car, "make": models.Make, "model": VehicleModel}


def _guard_tables(fn):
    """Translate missing-table errors into a clear 503."""
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (ProgrammingError, OperationalError) as e:
            if "does not exist" in str(e) or "no such table" in str(e):
                raise HTTPException(status_code=503, detail=MIGRATION_HINT)
            raise
    wrapper.__name__ = fn.__name__
    wrapper.__annotations__ = fn.__annotations__
    wrapper.__defaults__ = getattr(fn, "__defaults__", None)
    import inspect
    wrapper.__signature__ = inspect.signature(fn)
    return wrapper


# ---------- schemas ----------

class ProposalCreate(BaseModel):
    entity_type: str
    entity_id: int
    field: str
    old_value: Optional[object] = None
    new_value: Optional[object] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None


class ProposalBatch(BaseModel):
    proposals: List[ProposalCreate]
    crawl_run_id: Optional[int] = None


class ReviewAction(BaseModel):
    action: str  # 'approve' | 'reject'


class CrawlRunCreate(BaseModel):
    scope: str


class CrawlRunFinish(BaseModel):
    status: str = "completed"  # 'completed' | 'failed'
    stats: Optional[dict] = None


# ---------- crawl runs ----------

@router.post("/admin/crawl-runs")
@_guard_tables
async def start_crawl_run(
    body: CrawlRunCreate, db: db_dependency, admin: dict = Depends(get_admin_access)
):
    run = CrawlRun(scope=body.scope)
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "scope": run.scope, "started_at": str(run.started_at)}


@router.patch("/admin/crawl-runs/{run_id}")
@_guard_tables
async def finish_crawl_run(
    run_id: int,
    body: CrawlRunFinish,
    db: db_dependency,
    admin: dict = Depends(get_admin_access),
):
    run = db.query(CrawlRun).filter(CrawlRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Crawl run not found")
    run.status = body.status
    run.stats = body.stats or {}
    run.finished_at = datetime.utcnow()
    db.commit()
    return {"id": run.id, "status": run.status}


# ---------- proposals ----------

@router.post("/admin/proposals")
@_guard_tables
async def create_proposals(
    batch: ProposalBatch, db: db_dependency, admin: dict = Depends(get_admin_access)
):
    created, skipped = 0, 0
    for p in batch.proposals:
        if p.entity_type not in ALLOWED_FIELDS:
            raise HTTPException(status_code=422, detail=f"Unknown entity_type: {p.entity_type}")
        if p.field not in ALLOWED_FIELDS[p.entity_type]:
            raise HTTPException(
                status_code=422,
                detail=f"Field '{p.field}' is not crawler-writable for {p.entity_type}",
            )
        # Dedupe: identical pending proposal already in the inbox
        dup = (
            db.query(ChangeProposal)
            .filter(
                ChangeProposal.entity_type == p.entity_type,
                ChangeProposal.entity_id == p.entity_id,
                ChangeProposal.field == p.field,
                ChangeProposal.status == "pending",
            )
            .first()
        )
        if dup and dup.new_value == p.new_value:
            skipped += 1
            continue
        db.add(
            ChangeProposal(
                entity_type=p.entity_type,
                entity_id=p.entity_id,
                field=p.field,
                old_value=p.old_value,
                new_value=p.new_value,
                source_name=p.source_name,
                source_url=p.source_url,
                confidence=p.confidence,
                rationale=p.rationale,
                crawl_run_id=batch.crawl_run_id,
            )
        )
        created += 1
    db.commit()
    return {"created": created, "skipped_duplicates": skipped}


@router.get("/admin/proposals")
@_guard_tables
async def list_proposals(
    db: db_dependency,
    admin: dict = Depends(get_admin_access),
    status: str = "pending",
    limit: int = 100,
):
    rows = (
        db.query(ChangeProposal)
        .filter(ChangeProposal.status == status)
        .order_by(ChangeProposal.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )

    # Enrich with a human label for the inbox UI
    car_ids = [r.entity_id for r in rows if r.entity_type == "car"]
    labels = {}
    if car_ids:
        for cid, mk, mdl, sub in (
            db.query(models.Car.id, models.Car.make_name, models.Car.model, models.Car.submodel)
            .filter(models.Car.id.in_(car_ids))
            .all()
        ):
            labels[("car", cid)] = f"{mk} {mdl} {sub or ''}".strip()
    make_ids = [r.entity_id for r in rows if r.entity_type == "make"]
    if make_ids:
        for mid, name in db.query(models.Make.id, models.Make.name).filter(models.Make.id.in_(make_ids)).all():
            labels[("make", mid)] = name

    pending_total = db.query(ChangeProposal).filter(ChangeProposal.status == "pending").count()

    return {
        "pending_total": pending_total,
        "proposals": [
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "entity_label": labels.get((r.entity_type, r.entity_id), f"{r.entity_type} #{r.entity_id}"),
                "field": r.field,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "source_name": r.source_name,
                "source_url": r.source_url,
                "confidence": r.confidence,
                "rationale": r.rationale,
                "status": r.status,
                "created_at": str(r.created_at),
            }
            for r in rows
        ],
    }


@router.patch("/admin/proposals/{proposal_id}")
@_guard_tables
async def review_proposal(
    proposal_id: int,
    body: ReviewAction,
    db: db_dependency,
    admin: dict = Depends(get_admin_access),
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'reject'")

    prop = db.query(ChangeProposal).filter(ChangeProposal.id == proposal_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if prop.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal already {prop.status}")

    prop.reviewed_at = datetime.utcnow()

    if body.action == "reject":
        prop.status = "rejected"
        db.commit()
        return {"id": prop.id, "status": prop.status}

    # Approve → apply to the entity with provenance stamping
    if prop.field not in ALLOWED_FIELDS.get(prop.entity_type, set()):
        raise HTTPException(status_code=422, detail="Field no longer crawler-writable")
    orm = ENTITY_ORM[prop.entity_type]
    entity = db.query(orm).filter(orm.id == prop.entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail=f"{prop.entity_type} #{prop.entity_id} not found")

    setattr(entity, prop.field, prop.new_value)
    if hasattr(entity, "last_verified_at"):
        entity.last_verified_at = datetime.utcnow()
    if hasattr(entity, "sources") and prop.source_url:
        sources = list(entity.sources or [])
        entry = {"name": prop.source_name, "url": prop.source_url, "field": prop.field}
        if entry not in sources:
            sources.append(entry)
        entity.sources = sources

    prop.status = "approved"
    prop.applied_at = datetime.utcnow()
    db.commit()
    return {"id": prop.id, "status": prop.status, "applied_to": f"{prop.entity_type} #{prop.entity_id}"}
