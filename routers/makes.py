"""Make endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import subqueryload

import models.orm_models as models
from models.pydantic_models import MakeBase, MakeCreate, MakeRead, MakeUpdate
from auth import get_admin_access
from dependencies import db_dependency

router = APIRouter(tags=["makes"])


@router.get("/makes/{make_id}", response_model=MakeRead)
async def read_make(make_id: str, db: db_dependency):
    make = (
        db.query(models.Make)
        .options(subqueryload(models.Make.cars))
        .filter(models.Make.id == make_id)
        .first()
    )
    if not make:
        raise HTTPException(status_code=404, detail="Make not found")

    make_data = make.__dict__
    make_data["car_id_list"] = [car.id for car in make.cars]
    return make_data


@router.get("/makes", response_model=List[MakeRead])
async def read_makes(
    db: db_dependency, response: Response, skip: int = 0, limit: int = 100
):
    response.headers["Cache-Control"] = "public, s-maxage=3600, stale-while-revalidate=86400"
    makes = (
        db.query(models.Make)
        .options(subqueryload(models.Make.cars))
        .offset(skip)
        .limit(limit)
        .all()
    )
    result = []
    for make in makes:
        make_data = make.__dict__
        make_data["car_id_list"] = [car.id for car in make.cars]
        result.append(make_data)
    return result


@router.post("/makes", response_model=MakeCreate)
async def create_make(
    make: MakeBase, db: db_dependency, admin: dict = Depends(get_admin_access)
):
    make_data = make.model_dump(exclude_unset=True)
    db_make = models.Make(**make_data)
    db.add(db_make)
    db.commit()
    db.refresh(db_make)
    return db_make


@router.post("/makes/bulk", response_model=List[MakeCreate])
async def create_bulk_makes(
    makes: List[MakeBase], db: db_dependency, admin: dict = Depends(get_admin_access)
):
    db_makes = []
    for make in makes:
        db_make = models.Make(**make.model_dump())
        db.add(db_make)
        db_makes.append(db_make)
    db.commit()
    for make in db_makes:
        db.refresh(make)
    return db_makes


@router.patch("/makes/{make_id}", response_model=MakeUpdate)
async def update_make(
    make_id: int,
    make_update: MakeUpdate,
    db: db_dependency,
    admin: dict = Depends(get_admin_access),
):
    db_make = db.query(models.Make).filter(models.Make.id == make_id).first()
    if not db_make:
        raise HTTPException(status_code=404, detail="Make not found")

    update_data = make_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(db_make, key, value)

    # Update founders
    if make_update.founder_ids is not None:
        founders = (
            db.query(models.Person)
            .filter(models.Person.id.in_(make_update.founder_ids))
            .all()
        )
        if len(founders) != len(make_update.founder_ids):
            raise HTTPException(
                status_code=400, detail="One or more founder IDs not found"
            )
        db_make.founders = founders

    # Update key personnel
    if make_update.key_personnel_ids is not None:
        key_personnel = (
            db.query(models.Person)
            .filter(models.Person.id.in_(make_update.key_personnel_ids))
            .all()
        )
        if len(key_personnel) != len(make_update.key_personnel_ids):
            raise HTTPException(
                status_code=400, detail="One or more key personnel IDs not found"
            )
        db_make.key_personnel = key_personnel

    # Handle CEO updates with start and end dates
    if make_update.ceo_associations:
        db.query(models.make_ceo_association).filter_by(make_id=make_id).delete(
            synchronize_session=False
        )
        db.commit()

        for ceo_association in make_update.ceo_associations:
            new_ceo_assoc = models.make_ceo_association.insert().values(
                make_id=make_id,
                person_id=ceo_association.person_id,
                start_date=ceo_association.start_date,
                end_date=ceo_association.end_date,
            )
            db.execute(new_ceo_assoc)

    db.commit()
    db.refresh(db_make)
    return db_make
