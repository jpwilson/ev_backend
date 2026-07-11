"""User endpoints — profile, favorites, notes, garage cars."""

from typing import List, Optional
from datetime import datetime, date as date_type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_

from dependencies import db_dependency
from auth import get_current_user
from models.user_models import Profile, UserFavorite, UserNote, UserCar

router = APIRouter(prefix="/user", tags=["user"])


# --- Pydantic schemas ---

class ProfileRead(BaseModel):
    id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class FavoriteCreate(BaseModel):
    car_id: int


class FavoriteRead(BaseModel):
    id: int
    car_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NoteCreate(BaseModel):
    car_id: Optional[int] = None
    make_model_slug: Optional[str] = None
    title: Optional[str] = None
    content: str


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class NoteRead(BaseModel):
    id: int
    car_id: Optional[int] = None
    make_model_slug: Optional[str] = None
    title: Optional[str] = None
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserCarCreate(BaseModel):
    car_id: Optional[int] = None
    custom_make: Optional[str] = None
    custom_model: Optional[str] = None
    year: Optional[int] = None
    purchase_date: Optional[date_type] = None
    purchase_price: Optional[float] = None
    current_mileage: Optional[int] = None
    ownership_status: str = "owned"
    nickname: Optional[str] = None
    battery_health: Optional[float] = None
    notes: Optional[str] = None


class UserCarUpdate(BaseModel):
    current_mileage: Optional[int] = None
    ownership_status: Optional[str] = None
    nickname: Optional[str] = None
    battery_health: Optional[float] = None
    notes: Optional[str] = None


class UserCarRead(BaseModel):
    id: int
    car_id: Optional[int] = None
    custom_make: Optional[str] = None
    custom_model: Optional[str] = None
    year: Optional[int] = None
    purchase_date: Optional[date_type] = None
    purchase_price: Optional[float] = None
    current_mileage: Optional[int] = None
    ownership_status: Optional[str] = None
    nickname: Optional[str] = None
    battery_health: Optional[float] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Profile endpoints ---

@router.get("/me", response_model=ProfileRead)
async def get_my_profile(db: db_dependency, user: dict = Depends(get_current_user)):
    """Get the current user's profile."""
    profile = db.query(Profile).filter(Profile.id == user["sub"]).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/me", response_model=ProfileRead)
async def update_my_profile(
    update: ProfileUpdate,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.id == user["sub"]).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if update.display_name is not None:
        profile.display_name = update.display_name
    if update.avatar_url is not None:
        profile.avatar_url = update.avatar_url
    db.commit()
    db.refresh(profile)
    return profile


# --- Favorites endpoints ---

@router.get("/favorites", response_model=List[FavoriteRead])
async def get_favorites(db: db_dependency, user: dict = Depends(get_current_user)):
    return db.query(UserFavorite).filter(UserFavorite.user_id == user["sub"]).all()


@router.post("/favorites", response_model=FavoriteRead, status_code=201)
async def add_favorite(
    fav: FavoriteCreate,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    existing = db.query(UserFavorite).filter(
        and_(UserFavorite.user_id == user["sub"], UserFavorite.car_id == fav.car_id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Already favorited")
    db_fav = UserFavorite(user_id=user["sub"], car_id=fav.car_id)
    db.add(db_fav)
    db.commit()
    db.refresh(db_fav)
    return db_fav


@router.delete("/favorites/{car_id}", status_code=204)
async def remove_favorite(
    car_id: int,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    fav = db.query(UserFavorite).filter(
        and_(UserFavorite.user_id == user["sub"], UserFavorite.car_id == car_id)
    ).first()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")
    db.delete(fav)
    db.commit()


# --- Notes endpoints ---

@router.get("/notes", response_model=List[NoteRead])
async def get_notes(db: db_dependency, user: dict = Depends(get_current_user)):
    return db.query(UserNote).filter(UserNote.user_id == user["sub"]).order_by(UserNote.updated_at.desc()).all()


@router.post("/notes", response_model=NoteRead, status_code=201)
async def create_note(
    note: NoteCreate,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    db_note = UserNote(
        user_id=user["sub"],
        car_id=note.car_id,
        make_model_slug=note.make_model_slug,
        title=note.title,
        content=note.content,
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note


@router.patch("/notes/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: int,
    note_update: NoteUpdate,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    note = db.query(UserNote).filter(
        and_(UserNote.id == note_id, UserNote.user_id == user["sub"])
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note_update.title is not None:
        note.title = note_update.title
    if note_update.content is not None:
        note.content = note_update.content
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    note = db.query(UserNote).filter(
        and_(UserNote.id == note_id, UserNote.user_id == user["sub"])
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    db.delete(note)
    db.commit()


# --- Garage (user cars) endpoints ---

@router.get("/cars", response_model=List[UserCarRead])
async def get_my_cars(db: db_dependency, user: dict = Depends(get_current_user)):
    return db.query(UserCar).filter(UserCar.user_id == user["sub"]).order_by(UserCar.created_at.desc()).all()


@router.post("/cars", response_model=UserCarRead, status_code=201)
async def add_my_car(
    car: UserCarCreate,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    db_car = UserCar(user_id=user["sub"], **car.model_dump())
    db.add(db_car)
    db.commit()
    db.refresh(db_car)
    return db_car


@router.patch("/cars/{car_id}", response_model=UserCarRead)
async def update_my_car(
    car_id: int,
    car_update: UserCarUpdate,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    car = db.query(UserCar).filter(
        and_(UserCar.id == car_id, UserCar.user_id == user["sub"])
    ).first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found in your garage")
    update_data = car_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(car, key, value)
    db.commit()
    db.refresh(car)
    return car


@router.delete("/cars/{car_id}", status_code=204)
async def remove_my_car(
    car_id: int,
    db: db_dependency,
    user: dict = Depends(get_current_user),
):
    car = db.query(UserCar).filter(
        and_(UserCar.id == car_id, UserCar.user_id == user["sub"])
    ).first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found in your garage")
    db.delete(car)
    db.commit()
