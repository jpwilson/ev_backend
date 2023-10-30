from fastapi import FastAPI, HTTPException, Depends

from typing import Annotated, List, Optional
from sqlalchemy.orm import Session

from pydantic import BaseModel

from database import SessionLocal, engine
import models

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = ["http://localhost:3000", "http://localhost:5173"]

app.add_middleware(CORSMiddleware, allow_origins=origins)

from datetime import date


class CarBase(BaseModel):
    make_id: int
    model: str
    submodel: Optional[str]
    generation: Optional[str]
    image_url: Optional[str]
    trim_first_released: Optional[str]
    carmodel_first_released: Optional[str]
    current_price: Optional[float]
    customer_and_critic_rating: Optional[float]
    price_history: Optional[dict]  # Since we're using JSON columns
    vehicle_class: Optional[str]
    color_options: Optional[dict]
    performance_0_60: Optional[float]
    top_speed: Optional[float]
    power: Optional[float]
    torque: Optional[float]
    drive_type: Optional[str]
    battery_capacity: Optional[float]
    range_city_cold: Optional[float]
    range_highway_cold: Optional[float]
    range_combined_cold: Optional[float]
    range_highway_mid: Optional[float]
    range_city_mid: Optional[float]
    range_combined_mid: Optional[float]
    battery_max_charging_speed: Optional[float]
    yt_review_link: Optional[str]
    available_countries: Optional[dict]
    number_of_seats: Optional[int]
    has_frunk: Optional[bool]
    frunk_capacity: Optional[float]
    has_spare_tire: Optional[bool]
    autopilot_features: Optional[dict]
    euroncap_rating: Optional[str]
    nhtsa_rating: Optional[str]


class CarCreate(CarBase):
    pass


class CarRead(CarBase):
    id: int


class Car(CarBase):
    id: int

    class Config:
        orm_mode = True


class MakeBase(BaseModel):
    name: str
    ceo_pay: Optional[float]
    headquarters: Optional[str]
    founding_date: Optional[str]
    market_cap: Optional[float]
    revenue: Optional[float]
    num_ev_models: Optional[int]
    first_ev_model_date: Optional[str]
    unionized: Optional[bool]


class MakeCreate(MakeBase):
    pass


class MakeRead(MakeBase):
    id: int


class PersonBase(BaseModel):
    name: str
    age: Optional[int]
    location: Optional[str] = None
    university_degree: Optional[str] = None
    current_company: Optional[str] = None
    skills: Optional[str] = None
    strengths: Optional[dict] = {}
    weaknesses: Optional[dict] = {}


class PersonCreate(PersonBase):
    pass


class PersonRead(PersonBase):
    id: int


class Person(PersonBase):
    id: int

    class Config:
        orm_mode = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]

models.Base.metadata.create_all(bind=engine)


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


@app.get("/cars", response_model=List[CarRead])
async def read_cars(db: db_dependency, skip: int = 0, limit: int = 100):
    cars = db.query(models.Car).offset(skip).limit(limit).all()
    return cars


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


@app.get("/makes", response_model=List[MakeRead])
async def read_makes(db: db_dependency, skip: int = 0, limit: int = 100):
    makes = db.query(models.Make).offset(skip).limit(limit).all()
    return makes


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


@app.get("/people", response_model=List[PersonRead])
async def read_people(db: db_dependency, skip: int = 0, limit: int = 100):
    people = db.query(models.Person).offset(skip).limit(limit).all()
    return people
