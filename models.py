from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    Date,
    Boolean,
    JSON,
    Table,
)
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.ext.mutable import MutableDict

# ==== ASSOCIATION TABLES =======

# car_charger_association = Table(
#     "car_charger",
#     Base.metadata,
#     Column("car_id", Integer, ForeignKey("cars.id")),
#     Column("charger_id", Integer, ForeignKey("chargers.id")),
# )

# Association table for many-to-many relationship between Make and Person (founders)
make_person_association = Table(
    "make_person_association",
    Base.metadata,
    Column("make_id", Integer, ForeignKey("makes.id")),
    Column("person_id", Integer, ForeignKey("people.id")),
)

make_founders_association = Table(
    "make_founders_association",
    Base.metadata,
    Column("make_id", Integer, ForeignKey("makes.id")),
    Column("person_id", Integer, ForeignKey("people.id")),
)


class Car(Base):
    __tablename__ = "cars"

    # Basic Information
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    make = relationship(
        "Make", back_populates="cars"
    )  # Manufacturer e.g., Tesla, Nissan
    make_id = Column(Integer, ForeignKey("makes.id"))
    # make = Column(String)
    model = Column(String, index=True)  # Model e.g., Model S, Leaf
    submodel = Column(String)  # Trim level e.g., Long Range, Performance
    generation = Column(String)
    image_url = Column(String)  # Link to car image

    # Dates
    trim_first_released = Column(String)
    carmodel_first_released = Column(String)

    # Pricing
    current_price = Column(Float)
    price_history = Column(
        MutableDict.as_mutable(JSON), default={}
    )  # JSON serialized list of price changes with dates

    # Specifications
    customer_and_critic_rating = Column(Float)
    vehicle_class = Column(String)  # SUV, SEDAN etc.
    color_options = Column(
        MutableDict.as_mutable(JSON), default={}
    )  # JSON serialized list of available colors
    performance_0_60 = Column(Float)  # 0-60 mph time
    top_speed = Column(Float)
    power = Column(Float)
    torque = Column(Float)
    drive_type = Column(String)  # e.g., RWD, AWD
    battery_capacity = Column(Float)
    range_city_cold = Column(Float)
    range_highway_cold = Column(Float)
    range_combined_cold = Column(Float)
    range_highway_mid = Column(Float)
    range_city_mid = Column(Float)
    range_combined_mid = Column(Float)
    # ... Add other attributes in a similar manner ...

    # Charging
    battery_max_charging_speed = Column(Float)  # in kW
    chargers = Column(MutableDict.as_mutable(JSON), default={})
    # chargers = relationship(
    #     "Charger", secondary=car_charger_association, back_populates="cars"
    # )  # e.g.,  link to dif types in assoc. table Type 2, CCS, Tesla

    # Reviews
    yt_review_link = Column(String)  # Link to a YouTube review
    # ... More columns for other review platforms ...

    # Availability
    available_countries = Column(
        MutableDict.as_mutable(JSON), default={}
    )  # JSON serialized list of countries
    # ... Add state/province availability if necessary ...

    # Other Features
    number_of_seats = Column(Integer)
    has_frunk = Column(Boolean)
    frunk_capacity = Column(Float)  # in liters or cubic feet
    has_spare_tire = Column(Boolean)

    # Safety and Autonomy
    autopilot_features = Column(
        MutableDict.as_mutable(JSON), default={}
    )  # JSON serialized list of autopilot features
    euroncap_rating = Column(String)
    nhtsa_rating = Column(String)


class Make(Base):
    __tablename__ = "makes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True)

    # Detailed Information
    founders = relationship(
        "Person",
        secondary="make_founders_association",
        back_populates="founded_companies",
    )
    # CEO relationship
    ceo_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    ceo = relationship(
        "Person", uselist=False, backref="company_as_ceo"
    )  # One-to-one with Person

    # Key personnel relationship
    key_personnel = relationship(
        "Person",
        secondary=make_person_association,
        back_populates="car_companies_associated",
    )  # Assuming one CEO at a time
    ceo_pay = Column(Float)  # Salary or compensation of the CEO
    headquarters = Column(String)  # e.g., "Palo Alto, California, USA"
    founding_date = Column(String)  # Date when the company was founded
    market_cap = Column(
        Float
    )  # Company's current market capitalization in USD or other currency
    revenue = Column(Float)  # Annual revenue in USD or other currency
    num_ev_models = Column(Integer)  # Number of electric vehicle models they offer
    first_ev_model_date = Column(String)  # Release date of their first EV model
    # carmaker_locations = relationship(
    #    "CarmakerLocation", back_populates="makes"
    # )  # List of office locations, e.g., ["Palo Alto, CA", "Fremont, CA"]
    unionized = Column(Boolean, default=False)
    cars = relationship("Car", back_populates="make")


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    location = Column(String, nullable=True)
    university_degree = Column(String)  # Not making it required
    current_company = Column(String, nullable=True)
    skills = Column(String)
    strengths = Column(MutableDict.as_mutable(JSON), default={})
    weaknesses = Column(MutableDict.as_mutable(JSON), default={})
    car_companies_associated = relationship(
        "Make", secondary=make_person_association, back_populates="key_personnel"
    )
    founded_companies = relationship(
        "Make", secondary=make_founders_association, back_populates="founders"
    )
