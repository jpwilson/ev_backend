from database import SessionLocal  # Import your Session
from models.orm_models import Car  # Import your Car model


def populate_make_names():
    """
    Populates the make_name column for each car in the database.
    Should be run after adding the make_name column to the Car model.
    """
    db = SessionLocal()
    try:
        cars = db.query(Car).all()
        for car in cars:
            # Check if the car has a related make and set the make_name accordingly
            if car.make:
                car.make_name = car.make.name
            else:
                car.make_name = "Unknown"  # Or any other default value you see fit
            db.add(car)  # Stage the car for update

        # Commit the changes to the database
        db.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()  # Rollback the session in case of error
    finally:
        # Close the session
        db.close()


if __name__ == "__main__":
    populate_make_names()
