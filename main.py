from fastapi import FastAPI, HTTPException, Depends

from typing import Annotated, List, Optional, Dict
from sqlalchemy.orm import Session, joinedload, subqueryload

from pydantic import BaseModel, HttpUrl, Field

from database import SessionLocal, engine
import models

from fastapi.middleware.cors import CORSMiddleware

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


class Review(BaseModel):
    description: str
    url: str  # HttpUrl


class StrengthWeaknessItem(BaseModel):
    score: float
    description: str


class CarBase(BaseModel):
    make_id: int
    model: str
    submodel: Optional[str] = None
    generation: Optional[str] = None
    image_url: Optional[str] = None
    acceleration_0_60: Optional[float] = None
    current_price: Optional[float] = None
    epa_range: Optional[float] = None
    number_of_full_adult_seats: Optional[int] = None

    available_countries: Optional[Dict[str, List[str]]] = {}

    # charging
    battery_capacity: Optional[float] = None
    battery_max_charging_speed: Optional[float] = None
    bidirectional_details: Optional[Dict[str, str]] = {}
    chargers: Optional[List[str]] = []

    # dates
    carmodel_first_released: Optional[str] = None
    carmodel_ended: Optional[str] = None
    trim_first_released: Optional[str] = None
    trim_ended: Optional[str] = None

    color_options: Optional[
        Dict[str, List[str]]
    ] = {}  # the year is the key + list of colors as val

    customer_and_critic_rating: Optional[
        Dict[str, float]
    ] = {}  # dict of publication: rating

    drive_assist_features: Optional[List[str]] = None
    drive_type: Optional[str] = None
    frunk_capacity: Optional[float] = None

    has_spare_tire: Optional[bool] = None

    # performance
    power: Optional[float] = None
    top_speed: Optional[float] = None
    torque: Optional[float] = None
    speed_acc: Optional[Dict[str, float]] = {}

    # price
    price_history: Optional[Dict[str, float]] = {}  # Corrected type annotation

    range_details: Optional[Dict[str, float]] = {}  # Dict of  condition:range
    reviews: List[Review] = []

    # safety
    euroncap_rating: Optional[float] = None
    nhtsa_rating: Optional[float] = None
    sentry_security: Optional[bool] = None
    sentry_details: Optional[Dict[str, str]] = {}  # name, desc eg sentry, videos lose

    camping_features: Optional[Dict[str, str]] = {}
    dog_mode: Optional[Dict[str, str]] = {}  # has_dog_mode:y/n, dog_mode_desc, alter
    infotainment_details: Optional[Dict[str, str]] = {}
    interior_ambient_lighting_details: Optional[Dict[str, str]] = {}
    keyless: Optional[bool] = None
    number_of_passenger_doors: Optional[int] = None
    remote_heating_cooling: Optional[Dict[str, str]] = {}
    seating_details: Optional[Dict[str, str]] = {}
    towing_details: Optional[Dict[str, str]] = {}
    regen_details: Optional[Dict[str, str]] = {}
    vehicle_class: Optional[str] = None
    vehicle_sound_details: Optional[Dict[str, str]] = {}


class CarCreate(CarBase):
    pass


class CarRead(CarBase):
    id: int
    average_rating: float
    make_id: int
    make_name: str


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
    lrg_logo_img_url: Optional[str]


class MakeCreate(MakeBase):
    pass


class MakeRead(MakeBase):
    id: int
    car_id_list: List[int] = []


class PersonBase(BaseModel):
    name: str
    age: Optional[int]
    location: Optional[str] = None
    university_degree: Optional[str] = None
    current_company: Optional[str] = None
    skills: Optional[List[str]] = None
    # strengths: Optional[Dict[str, Union[str, int]]] = {}
    # weaknesses: Optional[Dict[str, Union[str, int]]] = {}
    strengths: Optional[Dict[str, StrengthWeaknessItem]] = Field(default_factory=dict)
    weaknesses: Optional[Dict[str, StrengthWeaknessItem]] = Field(default_factory=dict)


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


@app.patch("/cars/{car_id}/", response_model=Car)
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


@app.patch("/people/{person_id}/", response_model=Person)
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
