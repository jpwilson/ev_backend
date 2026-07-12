"""ORM models for the data-freshness pipeline (migrations 002 + 003).

Tables are created by SQL migrations in Supabase, not create_all — these
classes exist only so FastAPI routes can query them.
"""

from sqlalchemy import (
    Column, Integer, BigInteger, Text, Float, DateTime, Date, Numeric,
    ForeignKey, JSON,
)
from sqlalchemy.sql import func

from database import Base


class VehicleModel(Base):
    """First-class Model entity: makes -> models -> cars (trims)."""

    __tablename__ = "models"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    make_id = Column(Integer, ForeignKey("makes.id"))
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, unique=True)
    body_style = Column(Text)
    status = Column(Text, nullable=False, default="in_production")
    update_cadence = Column(Text, nullable=False, default="model_year")
    announced_date = Column(Date)
    launch_date = Column(Date)
    discontinued_date = Column(Date)
    description = Column(Text)
    official_url = Column(Text)
    popularity_rank = Column(Integer)
    last_verified_at = Column(DateTime(timezone=True))
    sources = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scope = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="running")
    stats = Column(JSON, default=dict)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))


class ChangeProposal(Base):
    __tablename__ = "change_proposals"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(Integer, nullable=False)
    field = Column(Text, nullable=False)
    old_value = Column(JSON)
    new_value = Column(JSON)
    source_name = Column(Text)
    source_url = Column(Text)
    confidence = Column(Float)
    rationale = Column(Text)
    status = Column(Text, nullable=False, default="pending")
    crawl_run_id = Column(BigInteger, ForeignKey("crawl_runs.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True))
    applied_at = Column(DateTime(timezone=True))


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    car_id = Column(Integer, ForeignKey("cars.id"), nullable=False)
    market = Column(Text, nullable=False, default="US")
    currency = Column(Text, nullable=False, default="USD")
    msrp = Column(Numeric(12, 2))
    effective_price = Column(Numeric(12, 2))
    source_url = Column(Text)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())
