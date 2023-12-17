import os
from datetime import date
from fastapi import FastAPI, HTTPException, Depends, Header, Request

from typing import Annotated, List, Optional, Dict
from fastapi.responses import JSONResponse
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
    CarUpdate,
    CarCreate,
    CarRead,
    MakeBase,
    MakeCreate,
    MakeRead,
    MakeUpdate,
    PersonBase,
    PersonCreate,
    PersonRead,
)

from dotenv import load_dotenv
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader


load_dotenv()  # take environment variables from .env here

API_KEY = os.getenv("API_SECRET_KEY", "no_key")
API_KEY_NAME = os.getenv("API_SECRET_KEY_NAME", "no_key_name")
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials here",
        )


app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:4173",
    "https://eeveecars.vercel.app",
    "https://www.evlineup.org",
    "https://evlineup.org",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET"],
    allow_credentials=True,
    allow_headers=["*"],
)  # Only allow GET requests

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


@app.get("/")
async def wel():
    return "Yo myman, it should work now - but others won't w/o access"


@app.get("/cars/model-reps", response_model=List[CarRead])
async def read_representative_models(
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    representative_cars = (
        db.query(models.Car).filter(models.Car.is_model_rep == True).all()
    )
    for car in representative_cars:
        car.average_rating = calculate_average_rating(car.customer_and_critic_rating)

    return representative_cars


@app.get("/cars/submodels/{make_model_slug}", response_model=List[CarRead])
async def read_submodels(
    make_model_slug: str,
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    submodels = (
        db.query(models.Car).filter(models.Car.make_model_slug == make_model_slug).all()
    )
    for car in submodels:
        car.average_rating = calculate_average_rating(car.customer_and_critic_rating)
    return submodels


@app.get("/cars/{car_id}", response_model=CarRead)
async def read_car_by_id(
    car_id: int, db: db_dependency, api_key: str = Depends(get_api_key)
):
    try:
        car = db.query(models.Car).filter(models.Car.id == car_id).first()
        print("did we get here??")
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
        print("no, we didn't get in to the try block...")
        raise HTTPException(
            status_code=404,
            detail=f"Car not found, are you sure {car_id} the correct car id?",
        )
        # return JSONResponse(status_code=500, content={"message": str(e)})


@app.post("/cars", response_model=CarCreate)
async def create_car(
    car: CarBase, db: db_dependency, api_key: str = Depends(get_api_key)
):
    db_car = models.Car(**car.model_dump())
    db.add(db_car)
    db.commit()
    db.refresh(db_car)
    return db_car


@app.post("/cars/bulk", response_model=List[CarCreate])
async def create_bulk_cars(
    cars: List[CarBase], db: db_dependency, api_key: str = Depends(get_api_key)
):
    db_cars = []
    for car in cars:
        db_car = models.Car(**car.model_dump())
        db.add(db_car)
        db_cars.append(db_car)
    db.commit()
    for car in db_cars:
        db.refresh(car)
    return db_cars


@app.patch("/cars/{car_id}", response_model=CarUpdate)
async def update_car(
    car_id: int,
    car_update: CarUpdate,
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    db_car = db.query(models.Car).filter(models.Car.id == car_id).first()
    if not db_car:
        raise HTTPException(status_code=404, detail="Car not found")

    update_data = car_update.model_dump(
        exclude_unset=True
    )  # Only fields provided in the PATCH request will be updated
    for key, value in update_data.items():
        if value is not None:
            setattr(db_car, key, value)

    db.commit()
    db.refresh(db_car)
    return db_car


@app.get("/cars", response_model=List[CarRead])
async def read_cars(
    db: db_dependency,
    skip: int = 0,
    limit: int = 100,
    api_key: str = Depends(get_api_key),
):
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
async def read_car_features(db: db_dependency, api_key: str = Depends(get_api_key)):
    cars = db.query(models.Car).all()
    car_features = bucket_cars_by_attributes(cars)
    return car_features


@app.get("/makes/{make_id}", response_model=MakeRead)
async def read_make(
    make_id: str,
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    make = db.query(models.Make).filter(models.Make.id == make_id).first()
    if not make:
        raise HTTPException(status_code=404, detail="Make not found")

    make_data = make.__dict__
    make_data["car_id_list"] = [car.id for car in make.cars]

    return make_data


@app.post("/makes", response_model=MakeCreate)
async def create_make(
    make: MakeBase, db: db_dependency, api_key: str = Depends(get_api_key)
):
    make_data = make.model_dump(exclude_unset=True)
    db_make = models.Make(**make_data)

    db.add(db_make)
    db.commit()
    db.refresh(db_make)
    return db_make


@app.post("/makes/bulk", response_model=List[MakeCreate])
async def create_bulk_makes(
    makes: List[MakeBase], db: db_dependency, api_key: str = Depends(get_api_key)
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


@app.patch("/makes/{make_id}", response_model=MakeUpdate)
async def update_make(
    make_id: int,
    make_update: MakeUpdate,
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    db_make = db.query(models.Make).filter(models.Make.id == make_id).first()
    print(f"This is what db_make name is: {db_make}")
    if not db_make:
        raise HTTPException(status_code=404, detail="Make not found")

    update_data = make_update.model_dump(exclude_unset=True)
    print(update_data, "  <--- this is the attribute on the make model ()")
    for key, value in update_data.items():
        print(f"key: {key}, value:{value}")
        if value is not None:
            setattr(db_make, key, value)

    # Check and update the founders
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

    # Check and update the key personnel
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
        # Remove current associations for this make
        # (consider whether you want to remove or update existing entries)
        db.query(models.make_ceo_association).filter_by(make_id=make_id).delete(
            synchronize_session=False
        )
        db.commit()  # Commit the deletions before adding new associations

        # Insert new CEO associations with start and end dates
        for ceo_association in make_update.ceo_associations:
            # Create a new CEO association record
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


@app.get("/makes", response_model=List[MakeRead])
async def read_makes(
    db: db_dependency,
    skip: int = 0,
    limit: int = 100,
    api_key: str = Depends(get_api_key),
):
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


@app.post("/people", response_model=PersonCreate)
async def create_person(
    person: PersonBase, db: db_dependency, api_key: str = Depends(get_api_key)
):
    db_person = models.Person(**person.model_dump())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


@app.post("/people/bulk", response_model=List[PersonCreate])
async def create_bulk_people(
    people: List[PersonBase], db: db_dependency, api_key: str = Depends(get_api_key)
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


@app.patch("/people/{person_id}", response_model=PersonCreate)
async def update_person(
    person_id: int,
    person_data: PersonBase,
    db: db_dependency,
    api_key: str = Depends(get_api_key),
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


@app.get("/people", response_model=List[PersonRead])
async def read_people(
    db: db_dependency,
    skip: int = 0,
    limit: int = 100,
    api_key: str = Depends(get_api_key),
):
    people = db.query(models.Person).offset(skip).limit(limit).all()
    return people
