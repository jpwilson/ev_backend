"""People endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException

import models.orm_models as models
from models.pydantic_models import PersonBase, PersonCreate, PersonRead
from dependencies import db_dependency, get_api_key, get_admin_api_key

router = APIRouter(tags=["people"])


@router.get("/people", response_model=List[PersonRead])
async def read_people(
    db: db_dependency,
    skip: int = 0,
    limit: int = 100,
    api_key: str = Depends(get_api_key),
):
    people = db.query(models.Person).offset(skip).limit(limit).all()
    return people


@router.post("/people", response_model=PersonCreate)
async def create_person(
    person: PersonBase, db: db_dependency, api_key: str = Depends(get_admin_api_key)
):
    db_person = models.Person(**person.model_dump())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


@router.post("/people/bulk", response_model=List[PersonCreate])
async def create_bulk_people(
    people: List[PersonBase], db: db_dependency, api_key: str = Depends(get_admin_api_key)
):
    db_people = []
    for person in people:
        db_person = models.Person(**person.model_dump())
        db.add(db_person)
        db_people.append(db_person)
    db.commit()
    for person in db_people:
        db.refresh(person)
    return db_people


@router.patch("/people/{person_id}", response_model=PersonCreate)
async def update_person(
    person_id: int,
    person_data: PersonBase,
    db: db_dependency,
    api_key: str = Depends(get_admin_api_key),
):
    db_person = db.query(models.Person).filter(models.Person.id == person_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="Person not found")

    for key, value in person_data.dict().items():
        if value is not None:
            setattr(db_person, key, value)

    db.commit()
    db.refresh(db_person)
    return db_person
