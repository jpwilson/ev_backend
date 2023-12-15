from database import SessionLocal  # Import your Session
from sqlalchemy.orm import joinedload
from models.orm_models import Car  # Import your Car model
from services.slug_service import SlugService  # Import SlugService


def populate_slugs():
    db = SessionLocal()
    try:
        # cars = db.query(Car).all()
        cars = (
            db.query(Car).options(joinedload(Car.make)).all()
        )  # Eagerly load the 'make' relationship
        for car in cars:
            if car.make and car.model:
                car.full_slug = SlugService.create_slug(
                    car.make.name, car.model, car.submodel
                )
                car.make_model_slug = SlugService.create_slug(car.make.name, car.model)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    populate_slugs()
