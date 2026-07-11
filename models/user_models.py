"""User-related ORM models.

These tables are created via Supabase SQL migrations (not SQLAlchemy create_all),
because they need RLS policies, triggers, and reference auth.users.
The ORM models here are used only for SQLAlchemy queries in FastAPI routes.
"""

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Numeric,
    Date, Text, ForeignKey, UniqueConstraint, Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from database import Base


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True)
    display_name = Column(Text)
    avatar_url = Column(Text)
    role = Column(Text, nullable=False, default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "car_id"),
        {"extend_existing": True},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    car_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserNote(Base):
    __tablename__ = "user_notes"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    car_id = Column(Integer, nullable=True)
    make_model_slug = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserCar(Base):
    __tablename__ = "user_cars"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    car_id = Column(Integer, nullable=True)
    custom_make = Column(Text)
    custom_model = Column(Text)
    year = Column(Integer)
    purchase_date = Column(Date)
    purchase_price = Column(Numeric(10, 2))
    current_mileage = Column(Integer)
    ownership_status = Column(Text, default="owned")
    nickname = Column(Text)
    battery_health = Column(Numeric(5, 2))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
