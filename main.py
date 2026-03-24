import os
import re
from datetime import date, datetime
from fastapi import FastAPI, HTTPException, Depends, Header, Request

from typing import Annotated, List, Optional, Dict
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session, joinedload, subqueryload
from sqlalchemy import func as sa_func

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
    MakeDetails,
    MakeRead,
    MakeUpdate,
    ModelDetailResponse,
    PersonBase,
    PersonCreate,
    PersonRead,
    PreviousGeneration,
    SubmodelInfo,
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
    ContactRequest,
    ContactResponse,
    PaginatedCarsResponse,
)

from dotenv import load_dotenv
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader


load_dotenv()  # take environment variables from .env here

API_KEY = os.getenv("API_SECRET_KEY", "no_key")
API_KEY_NAME = os.getenv("API_SECRET_KEY_NAME", "no_key_name")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials here",
        )


async def get_admin_api_key(
    api_key_header: str = Security(api_key_header),
    admin_key: str = Security(admin_key_header),
):
    if api_key_header != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    if not ADMIN_SECRET_KEY or admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key",
        )
    return admin_key


app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:4173",
    "https://eeveecars.vercel.app",
    "https://eeveecars-mc7i63xu9-jpwilsons-projects.vercel.app",
    "https://www.evlineup.org",
    "https://evlineup.org",
    "http://evlineup.org",
    "https://ev-backend-three.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_credentials=True,
    allow_headers=["*"],
)

# TODO - move helper methods to a new folder/ file... (Tues 14Nov 2023)
# helper models:


def calculate_average_rating(ratings: Optional[Dict[str, float]]) -> float:
    # note Im making this mult by 2 as I set ratings between 0 and 10 in react!!!
    if ratings:
        total = sum(ratings.values())
        count = len(ratings)
        return round((total / count), 2) if count else 0
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


@app.get("/cars/model-reps", response_model=PaginatedCarsResponse)
async def read_representative_models(
    db: db_dependency,
    api_key: str = Depends(get_api_key),
    limit: Optional[int] = None,
    offset: int = 0,
):
    """Get representative models with optional pagination.

    - If limit is omitted, returns ALL model reps (backwards-compatible).
    - If limit is provided, returns paginated results with total count.
    """
    base_query = (
        db.query(models.Car)
        .options(joinedload(models.Car.make))
        .filter(models.Car.is_model_rep == True)
    )

    total = base_query.count()

    if limit is not None:
        representative_cars = base_query.offset(offset).limit(limit).all()
    else:
        representative_cars = base_query.all()

    for car in representative_cars:
        car.average_rating = calculate_average_rating(car.customer_and_critic_rating)
        if car.make and not car.make_name:
            car.make_name = car.make.name

    return PaginatedCarsResponse(
        items=representative_cars,
        total=total,
        limit=limit if limit is not None else total,
        offset=offset,
    )


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


@app.get("/cars/model-details/{make_model_slug}", response_model=ModelDetailResponse)
async def read_model_details_and_submodels(
    make_model_slug: str,
    db: db_dependency,
    api_key: str = Depends(get_api_key),
):
    # Find the representative model
    representative_model = (
        db.query(models.Car)
        .filter(
            models.Car.make_model_slug == make_model_slug,
            models.Car.is_model_rep == True,
        ).options(joinedload(models.Car.make))
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
    
    # Extract make details
    make_details = None
    if representative_model.make:
        make_details = MakeDetails.from_orm(representative_model.make)
    
    # Fetch and process the submodels as you have been doing

    # Get simplified data for all submodels (including previous generations)
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

    # Separate current submodels from previous generations
    current_submodels = []
    prev_gen_map = {}  # generation -> list of SubmodelInfo

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

    # Build previous generations list
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


@app.get("/admin/verify")
async def verify_admin_key(admin_key: str = Depends(get_admin_api_key)):
    return {"status": "ok", "message": "Admin key verified"}


@app.post("/cars", response_model=CarCreate)
async def create_car(
    car: CarBase, db: db_dependency, api_key: str = Depends(get_admin_api_key)
):
    db_car = models.Car(**car.model_dump())
    db.add(db_car)
    db.commit()
    db.refresh(db_car)
    return db_car


@app.post("/cars/bulk", response_model=List[CarCreate])
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


@app.patch("/cars/{car_id}", response_model=CarUpdate)
async def update_car(
    car_id: int,
    car_update: CarUpdate,
    db: db_dependency,
    api_key: str = Depends(get_admin_api_key),
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


@app.get("/cars/admin-list")
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


@app.post("/makes", response_model=MakeCreate)
async def create_make(
    make: MakeBase, db: db_dependency, api_key: str = Depends(get_admin_api_key)
):
    make_data = make.model_dump(exclude_unset=True)
    db_make = models.Make(**make_data)

    db.add(db_make)
    db.commit()
    db.refresh(db_make)
    return db_make


@app.post("/makes/bulk", response_model=List[MakeCreate])
async def create_bulk_makes(
    makes: List[MakeBase], db: db_dependency, api_key: str = Depends(get_admin_api_key)
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
    api_key: str = Depends(get_admin_api_key),
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
    person: PersonBase, db: db_dependency, api_key: str = Depends(get_admin_api_key)
):
    db_person = models.Person(**person.model_dump())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


@app.post("/people/bulk", response_model=List[PersonCreate])
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


@app.patch("/people/{person_id}", response_model=PersonCreate)
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


@app.get("/people", response_model=List[PersonRead])
async def read_people(
    db: db_dependency,
    skip: int = 0,
    limit: int = 100,
    api_key: str = Depends(get_api_key),
):
    people = db.query(models.Person).offset(skip).limit(limit).all()
    return people


# ==================== NEWSLETTER ====================


@app.post("/api/newsletter/subscribe", response_model=NewsletterSubscribeResponse)
async def newsletter_subscribe(
    payload: NewsletterSubscribeRequest,
    db: db_dependency,
):
    """Subscribe an email to the newsletter. Handles duplicates via upsert."""
    email = payload.email.strip().lower()

    # Basic email validation
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    existing = (
        db.query(models.NewsletterSubscriber)
        .filter(models.NewsletterSubscriber.email == email)
        .first()
    )

    if existing:
        # Re-subscribe if previously unsubscribed
        if existing.unsubscribed_at is not None:
            existing.unsubscribed_at = None
            existing.subscribed_at = datetime.utcnow()
            db.commit()
            return NewsletterSubscribeResponse(
                message="Successfully re-subscribed",
                email=email,
                already_subscribed=False,
            )
        return NewsletterSubscribeResponse(
            message="Email is already subscribed",
            email=email,
            already_subscribed=True,
        )

    subscriber = models.NewsletterSubscriber(email=email)
    db.add(subscriber)
    db.commit()
    return NewsletterSubscribeResponse(
        message="Successfully subscribed",
        email=email,
        already_subscribed=False,
    )


# ==================== CONTACT FORM ====================


@app.post("/api/contact", response_model=ContactResponse)
async def contact_submit(
    payload: ContactRequest,
    db: db_dependency,
):
    """Store a contact form submission."""
    submission = models.ContactSubmission(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        message=payload.message.strip(),
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return ContactResponse(
        message="Message received. We'll get back to you soon.",
        id=submission.id,
    )


# ==================== DYNAMIC SITEMAP ====================

FRONTEND_BASE_URL = "https://www.evlineup.org"


@app.get("/sitemap.xml")
async def sitemap_xml(db: db_dependency):
    """Generate a dynamic sitemap with all public pages, car models, and manufacturers."""

    # Static pages
    static_pages = [
        {"loc": "/", "priority": "1.0", "changefreq": "weekly"},
        {"loc": "/about", "priority": "0.5", "changefreq": "monthly"},
    ]

    # Fetch all model-rep cars for model detail pages
    cars = (
        db.query(
            models.Car.make_model_slug,
            models.Car.id,
            models.Car.updated_at,
        )
        .filter(models.Car.is_model_rep == True)
        .all()
    )

    # Fetch all makes for manufacturer pages
    makes = (
        db.query(models.Make.id, models.Make.name, models.Make.updated_at)
        .all()
    )

    # Build XML
    urls = []

    for page in static_pages:
        urls.append(
            f'  <url>\n'
            f'    <loc>{FRONTEND_BASE_URL}{page["loc"]}</loc>\n'
            f'    <changefreq>{page["changefreq"]}</changefreq>\n'
            f'    <priority>{page["priority"]}</priority>\n'
            f'  </url>'
        )

    for car in cars:
        lastmod = ""
        if car.updated_at:
            lastmod = f"\n    <lastmod>{car.updated_at.strftime('%Y-%m-%d')}</lastmod>"
        # Model detail page
        if car.make_model_slug:
            urls.append(
                f'  <url>\n'
                f'    <loc>{FRONTEND_BASE_URL}/model_detail/{car.make_model_slug}</loc>{lastmod}\n'
                f'    <changefreq>weekly</changefreq>\n'
                f'    <priority>0.8</priority>\n'
                f'  </url>'
            )
        # Car detail page by ID
        urls.append(
            f'  <url>\n'
            f'    <loc>{FRONTEND_BASE_URL}/car_detail/{car.id}</loc>{lastmod}\n'
            f'    <changefreq>weekly</changefreq>\n'
            f'    <priority>0.7</priority>\n'
            f'  </url>'
        )

    for make in makes:
        lastmod = ""
        if make.updated_at:
            lastmod = f"\n    <lastmod>{make.updated_at.strftime('%Y-%m-%d')}</lastmod>"
        make_slug = make.name.lower().replace(" ", "-") if make.name else str(make.id)
        urls.append(
            f'  <url>\n'
            f'    <loc>{FRONTEND_BASE_URL}/manufacturer/{make_slug}</loc>{lastmod}\n'
            f'    <changefreq>monthly</changefreq>\n'
            f'    <priority>0.6</priority>\n'
            f'  </url>'
        )

    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )

    return Response(content=xml_content, media_type="application/xml")


# ==================== PRE-RENDERING / OG META SUPPORT ====================


@app.get("/api/og-meta/{path:path}")
async def og_meta(path: str, db: db_dependency):
    """Return OG meta tags as HTML for social media crawlers.

    Use with Vercel rewrites to serve this to crawlers (facebookexternalhit,
    Twitterbot, LinkedInBot, etc.) while serving the SPA to regular users.
    """
    title = "EV Lineup — Electric Vehicle Comparison"
    description = "Compare electric vehicles side by side. Specs, pricing, range, and reviews for every EV on the market."
    image = f"{FRONTEND_BASE_URL}/og-default.png"
    url = f"{FRONTEND_BASE_URL}/{path}"

    # Model detail page: /model_detail/{slug}
    if path.startswith("model_detail/"):
        slug = path.replace("model_detail/", "")
        car = (
            db.query(models.Car)
            .options(joinedload(models.Car.make))
            .filter(
                models.Car.make_model_slug == slug,
                models.Car.is_model_rep == True,
            )
            .first()
        )
        if car:
            make_name = car.make_name or (car.make.name if car.make else "")
            title = f"{make_name} {car.model} — EV Lineup"
            description = car.model_description or car.car_description or f"Compare {make_name} {car.model} specs, range, pricing, and reviews."
            if car.image_url:
                image = car.image_url

    # Car detail page: /car_detail/{id}
    elif path.startswith("car_detail/"):
        car_id_str = path.replace("car_detail/", "")
        if car_id_str.isdigit():
            car = (
                db.query(models.Car)
                .options(joinedload(models.Car.make))
                .filter(models.Car.id == int(car_id_str))
                .first()
            )
            if car:
                make_name = car.make_name or (car.make.name if car.make else "")
                submodel = f" {car.submodel}" if car.submodel else ""
                title = f"{make_name} {car.model}{submodel} — EV Lineup"
                description = car.car_description or f"Detailed specs, pricing, and reviews for the {make_name} {car.model}{submodel}."
                if car.image_url:
                    image = car.image_url

    # Manufacturer page: /manufacturer/{slug}
    elif path.startswith("manufacturer/"):
        make_slug = path.replace("manufacturer/", "")
        make = (
            db.query(models.Make)
            .filter(sa_func.lower(models.Make.name) == make_slug.replace("-", " "))
            .first()
        )
        if make:
            title = f"{make.name} Electric Vehicles — EV Lineup"
            description = make.description or f"Explore all {make.name} electric vehicles, specs, and pricing."
            if make.lrg_logo_img_url:
                image = make.lrg_logo_img_url

    # Truncate description for OG tags
    if len(description) > 200:
        description = description[:197] + "..."

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:image" content="{image}" />
    <meta property="og:url" content="{url}" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{title}" />
    <meta name="twitter:description" content="{description}" />
    <meta name="twitter:image" content="{image}" />
    <meta name="description" content="{description}" />
</head>
<body>
    <p>{description}</p>
    <p><a href="{url}">View on EV Lineup</a></p>
</body>
</html>"""

    return Response(content=html, media_type="text/html")
