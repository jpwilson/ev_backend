from fastapi import FastAPI, HTTPException, Depends

from typing import Annotated, List, Optional, Dict
from sqlalchemy.orm import Session, joinedload, subqueryload

from pydantic import BaseModel, HttpUrl, Field

from database import SessionLocal, engine
import models.orm_models as models

from services.car_features import bucket_cars_by_attributes

from fastapi.middleware.cors import CORSMiddleware

from models.pydantic_models import (
    Review,
    StrengthWeaknessItem,
    CarBase,
    CarCreate,
    CarRead,
    MakeBase,
    MakeCreate,
    MakeRead,
    PersonBase,
    PersonCreate,
    PersonRead,
)

from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env

app = FastAPI()

origins = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"]

app.add_middleware(CORSMiddleware, allow_origins=origins)

from datetime import date

# TODO - move helper methods to a new folder/ file... (Tues 14Nov 2023)
# helper models:


def calculate_average_rating(ratings: Optional[Dict[str, float]]) -> float:
    # note Im making this mult by 2 as I set ratings between 0 and 10 in react!!!
    if ratings:
        total = sum(ratings.values())
        count = len(ratings)
        return round((total / count), 2) * 2 if count else 0
    return 0


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]

models.Base.metadata.create_all(bind=engine)


@app.get("/cars/{car_id}", response_model=CarRead)
async def read_car_by_id(car_id: int, db: db_dependency):
    try:
        car = db.query(models.Car).filter(models.Car.id == car_id).first()
        if car:
            car_data = car.__dict__
            car_data["average_rating"] = calculate_average_rating(
                car.customer_and_critic_rating
            )
            car_data["make_name"] = (
                car.make.name if car.make else None
            )  # Make sure 'make' relationship is correctly set up
            return car_data
        else:
            return JSONResponse(status_code=404, content={"message": "Car not found"})
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Car not found, are you sure {car_id} the correct car id?",
        )
        # return JSONResponse(status_code=500, content={"message": str(e)})


@app.post("/cars/", response_model=CarCreate)
async def create_car(car: CarBase, db: db_dependency):
    db_car = models.Car(**car.model_dump())
    db.add(db_car)
    db.commit()
    db.refresh(db_car)
    return db_car


@app.post("/cars/bulk/", response_model=List[CarCreate])
async def create_bulk_cars(cars: List[CarBase], db: db_dependency):
    db_cars = []
    for car in cars:
        db_car = models.Car(**car.model_dump())
        db.add(db_car)
        db_cars.append(db_car)
    db.commit()
    for car in db_cars:
        db.refresh(car)
    return db_cars


@app.patch("/cars/{car_id}/", response_model=CarRead)
async def update_car(car_id: int, car_data: CarBase, db: db_dependency):
    db_car = db.query(models.Car).filter(models.Car.id == car_id).first()
    if not db_car:
        raise HTTPException(status_code=404, detail="Car not found")

    for key, value in car_data.dict().items():
        if value is not None:
            setattr(db_car, key, value)

    db.commit()
    db.refresh(db_car)
    return db_car


@app.get("/cars", response_model=List[CarRead])
async def read_cars(db: db_dependency, skip: int = 0, limit: int = 100):
    cars = (
        db.query(models.Car)
        .options(joinedload(models.Car.make))
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Transforming the cars data to include make name
    result = []
    for car in cars:
        car_data = car.__dict__
        car_data[
            "make_name"
        ] = car.make.name  # Assuming you have a relationship set up named "make"
        car_data["average_rating"] = calculate_average_rating(
            car.customer_and_critic_rating
        )
        result.append(car_data)
    return result

    # cars = db.query(models.Car).offset(skip).limit(limit).all()
    # return cars


@app.get("/car_features")
async def read_car_features(db: db_dependency):
    cars = db.query(models.Car).all()
    car_features = bucket_cars_by_attributes(cars)
    return car_features


@app.post("/makes/", response_model=MakeCreate)
async def create_make(make: MakeBase, db: db_dependency):
    db_make = models.Make(**make.model_dump())
    db.add(db_make)
    db.commit()
    db.refresh(db_make)
    return db_make


@app.post("/makes/bulk/", response_model=List[MakeCreate])
async def create_bulk_makes(makes: List[MakeBase], db: db_dependency):
    db_makes = []
    for make in makes:
        db_make = models.Make(**make.model_dump())
        db.add(db_make)
        db_makes.append(db_make)
    db.commit()
    for make in db_makes:
        db.refresh(make)
    return db_makes


@app.patch("/makes/{make_name}/", response_model=MakeRead)
async def update_make(make_name: str, make: MakeBase, db: db_dependency):
    db_make = db.query(models.Make).filter(models.Make.name == make_name).first()
    if not db_make:
        raise HTTPException(status_code=404, detail="Make not found")

    for key, value in make.dict().items():
        if value is not None:
            setattr(db_make, key, value)

    db.commit()
    db.refresh(db_make)
    return db_make


@app.get("/makes", response_model=List[MakeRead])
async def read_makes(db: db_dependency, skip: int = 0, limit: int = 100):
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

    # makes = db.query(models.Make).offset(skip).limit(limit).all()
    # return makes


@app.post("/people/", response_model=PersonCreate)
async def create_person(person: PersonBase, db: db_dependency):
    db_person = models.Person(**person.model_dump())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


@app.post("/people/bulk/", response_model=List[PersonCreate])
async def create_bulk_people(people: List[PersonBase], db: db_dependency):
    db_people = []
    for person in people:
        db_person = models.Person(**person.model_dump())
        db.add(db_person)
        db_people.append(db_person)
    db.commit()
    for person in db_people:
        db.refresh(person)
    return db_people


@app.patch("/people/{person_id}/", response_model=PersonCreate)
async def update_person(person_id: int, person_data: PersonBase, db: db_dependency):
    db_person = db.query(models.Person).filter(models.Person.id == person_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="Person not found")

    for key, value in person_data.dict().items():
        if value is not None:
            setattr(db_person, key, value)

    db.commit()
    db.refresh(db_person)
    return db_person


@app.get("/people", response_model=List[PersonRead])
async def read_people(db: db_dependency, skip: int = 0, limit: int = 100):
    people = db.query(models.Person).offset(skip).limit(limit).all()
    return people
