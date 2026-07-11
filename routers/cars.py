"""Car endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import joinedload

import models.orm_models as models
from models.pydantic_models import (
    CarBase, CarUpdate, CarCreate, CarRead,
    ModelDetailResponse, MakeDetails, SubmodelInfo, PreviousGeneration,
)
from dependencies import db_dependency, get_api_key, get_admin_api_key, calculate_average_rating
from services.car_features import bucket_cars_by_attributes

router = APIRouter(tags=["cars"])


@router.get("/cars/model-reps", response_model=List[CarRead])
async def read_representative_models(
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    representative_cars = (
        db.query(models.Car)
        .options(joinedload(models.Car.make))
        .filter(models.Car.is_model_rep == True)
        .all()
    )
    for car in representative_cars:
        car.average_rating = calculate_average_rating(car.customer_and_critic_rating)
        if car.make and not car.make_name:
            car.make_name = car.make.name
    return representative_cars


@router.get("/cars/submodels/{make_model_slug}", response_model=List[CarRead])
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


@router.get("/cars/model-details/{make_model_slug}", response_model=ModelDetailResponse)
async def read_model_details_and_submodels(
    make_model_slug: str,
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    representative_model = (
        db.query(models.Car)
        .filter(
            models.Car.make_model_slug == make_model_slug,
            models.Car.is_model_rep == True,
        )
        .options(joinedload(models.Car.make))
        .first()
    )

    if representative_model:
        representative_model.average_rating = calculate_average_rating(
            representative_model.customer_and_critic_rating
        )
        if representative_model.make and not representative_model.make_name:
            representative_model.make_name = representative_model.make.name

    if not representative_model:
        raise HTTPException(status_code=404, detail="Representative model not found")

    make_details = None
    if representative_model.make:
        make_details = MakeDetails.from_orm(representative_model.make)

    submodels_data = (
        db.query(
            models.Car.id,
            models.Car.submodel,
            models.Car.image_url,
            models.Car.current_price,
            models.Car.acceleration_0_60,
            models.Car.top_speed,
            models.Car.epa_range,
            models.Car.generation,
            models.Car.availability_desc,
        )
        .filter(models.Car.make_model_slug == make_model_slug)
        .all()
    )

    current_submodels = []
    prev_gen_map = {}

    for row in submodels_data:
        id, submodel, image_url, current_price, acceleration_0_60, top_speed, epa_range, generation, availability_desc = row
        info = SubmodelInfo(
            id=id,
            submodel=submodel,
            image_url=image_url,
            current_price=current_price,
            acceleration_0_60=acceleration_0_60,
            top_speed=top_speed,
            epa_range=epa_range,
            generation=generation,
            availability_desc=availability_desc,
        )
        if availability_desc == "previous_generation":
            gen_key = generation or "Earlier Generation"
            if gen_key not in prev_gen_map:
                prev_gen_map[gen_key] = {"image_url": image_url, "submodels": []}
            prev_gen_map[gen_key]["submodels"].append(info)
        else:
            current_submodels.append(info)

    previous_generations = [
        PreviousGeneration(
            generation=gen_key,
            image_url=data["image_url"],
            submodels=data["submodels"],
        )
        for gen_key, data in prev_gen_map.items()
    ]

    return {
        "representative_model": representative_model,
        "submodels": current_submodels,
        "make_details": make_details,
        "previous_generations": previous_generations,
    }


@router.get("/cars/admin-list")
async def read_cars_admin_list(
    db: db_dependency,
    api_key: str = Depends(get_admin_api_key),
):
    """Return all cars with basic info for admin car picker."""
    cars = (
        db.query(
            models.Car.id,
            models.Car.make_name,
            models.Car.model,
            models.Car.submodel,
            models.Car.generation,
            models.Car.is_model_rep,
            models.Car.image_url,
            models.Car.availability_desc,
        )
        .order_by(models.Car.make_name, models.Car.model, models.Car.submodel)
        .all()
    )
    return [
        {
            "id": c.id,
            "make_name": c.make_name,
            "model": c.model,
            "submodel": c.submodel,
            "generation": c.generation,
            "is_model_rep": c.is_model_rep,
            "image_url": c.image_url,
            "availability_desc": c.availability_desc,
        }
        for c in cars
    ]


@router.get("/cars/{car_id}", response_model=CarRead)
async def read_car_by_id(
    car_id: int, db: db_dependency, api_key: str = Depends(get_api_key)
):
    try:
        car = db.query(models.Car).filter(models.Car.id == car_id).first()
        if car:
            car_data = car.__dict__
            car_data["average_rating"] = calculate_average_rating(
                car.customer_and_critic_rating
            )
            car_data["make_name"] = car.make.name if car.make else None
            return car_data
        else:
            return JSONResponse(status_code=404, content={"message": "Car not found"})
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Car not found, are you sure {car_id} the correct car id?",
        )


@router.get("/cars", response_model=List[CarRead])
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
    result = []
    for car in cars:
        car_data = car.__dict__
        car_data["make_name"] = car.make.name
        car_data["average_rating"] = calculate_average_rating(
            car.customer_and_critic_rating
        )
        result.append(car_data)
    return result


@router.get("/car_features")
async def read_car_features(db: db_dependency, api_key: str = Depends(get_api_key)):
    cars = db.query(models.Car).all()
    car_features = bucket_cars_by_attributes(cars)
    return car_features


@router.post("/cars", response_model=CarCreate)
async def create_car(
    car: CarBase, db: db_dependency, api_key: str = Depends(get_admin_api_key)
):
    db_car = models.Car(**car.model_dump())
    db.add(db_car)
    db.commit()
    db.refresh(db_car)
    return db_car


@router.post("/cars/bulk", response_model=List[CarCreate])
async def create_bulk_cars(
    cars: List[CarBase], db: db_dependency, api_key: str = Depends(get_admin_api_key)
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


@router.patch("/cars/{car_id}", response_model=CarUpdate)
async def update_car(
    car_id: int,
    car_update: CarUpdate,
    db: db_dependency,
    api_key: str = Depends(get_admin_api_key),
):
    db_car = db.query(models.Car).filter(models.Car.id == car_id).first()
    if not db_car:
        raise HTTPException(status_code=404, detail="Car not found")

    update_data = car_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(db_car, key, value)

    db.commit()
    db.refresh(db_car)
    return db_car
