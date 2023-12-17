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
    Text,
)
from sqlalchemy import event, inspect
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.ext.mutable import MutableDict, MutableList
from services.slug_service import SlugService

# ==== ASSOCIATION TABLES =======


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

make_ceo_association = Table(
    "make_ceo_association",
    Base.metadata,
    Column("make_id", Integer, ForeignKey("makes.id")),
    Column("person_id", Integer, ForeignKey("people.id")),
    # Possibly include additional columns for start and end dates
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
    desc = Column(Text, nullable=True)
    generation = Column(String)
    image_url = Column(String)  # Link to car image
    acceleration_0_60 = Column(Float)  # 0-60 mph time
    current_price = Column(Float)
    epa_range = Column(Float)
    number_of_full_adult_seats = Column(Integer)
    full_slug = Column(String, index=True, unique=True)
    make_model_slug = Column(String)
    is_model_rep = Column(
        Boolean, default=False, index=True
    )  # the model on model page representing all submodels

    # Availability
    available_countries = Column(
        MutableDict.as_mutable(JSON), default={}
    )  # JSON serialized list of countries
    # ... Add state/province availability if necessary ...

    # Charging
    battery_capacity = Column(Float)
    battery_max_charging_speed = Column(Float)  # in kW
    bidirectional_details = Column(MutableDict.as_mutable(JSON), default={})
    chargers = Column(
        MutableList.as_mutable(JSON), default=[]
    )  # Default to an empty list
    # chargers = relationship(
    #     "Charger", secondary=car_charger_association, back_populates="cars"
    # )  # e.g.,  link to dif types in assoc. table Type 2, CCS, Tesla

    # Dates
    carmodel_first_released = Column(String)
    carmodel_ended = Column(String)
    trim_ended = Column(String)
    trim_first_released = Column(String)

    color_options = Column(
        MutableDict.as_mutable(JSON), default={}
    )  # JSON serialized list of available colors

    customer_and_critic_rating = Column(MutableDict.as_mutable(JSON), default={})

    drive_assist_features = Column(MutableList.as_mutable(JSON), default=[])  # FSD, etc
    drive_type = Column(String)  # e.g., RWD, AWD
    frunk_capacity = Column(Float)  # in liters or cubic feet
    has_spare_tire = Column(Boolean)

    # Performance
    power = Column(Float)
    top_speed = Column(Float)
    torque = Column(Float)
    speed_acc = Column(MutableDict.as_mutable(JSON), default={})  # various acce

    # Pricing
    price_history = Column(
        MutableDict.as_mutable(JSON), default={}
    )  # JSON serialized list of price changes with dates

    reviews = Column(MutableList.as_mutable(JSON), default=[])
    range_details = Column(MutableDict.as_mutable(JSON), default={})

    # Safety
    euroncap_rating = Column(Float)
    nhtsa_rating = Column(Float)
    sentry_security = Column(Boolean)
    sentry_details = Column(MutableDict.as_mutable(JSON), default={})

    camping_features = Column(MutableDict.as_mutable(JSON), default={})
    dog_mode = Column(MutableDict.as_mutable(JSON), default={})
    infotainment_details = Column(MutableDict.as_mutable(JSON), default={})
    interior_ambient_lighting_details = Column(MutableDict.as_mutable(JSON), default={})
    keyless = Column(Boolean)
    number_of_passenger_doors = Column(Integer)
    remote_heating_cooling = Column(MutableDict.as_mutable(JSON), default={})
    seating_details = Column(MutableDict.as_mutable(JSON), default={})
    towing_details = Column(MutableDict.as_mutable(JSON), default={})
    regen_details = Column(
        MutableDict.as_mutable(JSON), default={}  # cna you change it,
    )
    vehicle_class = Column(String)  # SUV, SEDAN etc.
    vehicle_sound_details = Column(MutableDict.as_mutable(JSON), default={})


# Event listener for the Car model before an insert
@event.listens_for(Car, "before_insert")
def receive_before_insert(mapper, connection, target):
    # Generate the full make-model-submodel slug
    make_name = target.make.name if target.make else "unknown-make"
    model_name = target.model if target.model else "unknown-model"
    submodel_name = target.submodel if target.submodel else ""
    target.full_slug = SlugService.create_slug(make_name, model_name, submodel_name)
    # Generate the make-model slug
    target.make_model_slug = SlugService.create_slug(make_name, model_name)


# Event listener for the Car model before an update
@event.listens_for(Car, "before_update")
def receive_before_update(mapper, connection, target):
    # Check if any of the fields that make up the slugs have changed.
    # If so, update the slugs.
    if (
        inspect(target).attrs.make.loaded_value != target.make
        or inspect(target).attrs.model.loaded_value != target.model
        or inspect(target).attrs.submodel.loaded_value != target.submodel
    ):
        make_name = target.make.name if target.make else "unknown-make"
        model_name = target.model if target.model else "unknown-model"
        submodel_name = target.submodel if target.submodel else ""
        # Update the full make-model-submodel slug
        target.full_slug = SlugService.create_slug(make_name, model_name, submodel_name)
        # Update the make-model slug
        target.make_model_slug = SlugService.create_slug(make_name, model_name)


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
    ceos = relationship(
        "Person", secondary=make_ceo_association, back_populates="companies_as_ceo"
    )  # Assuming one CEO at a time

    ceo_pay = Column(Float)  # Salary or compensation of the CEO
    # Key personnel relationship
    key_personnel = relationship(
        "Person",
        secondary=make_person_association,
        back_populates="car_companies_associated",
    )

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
    lrg_logo_img_url = Column(String, nullable=True)
    cars = relationship("Car", back_populates="make")


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    location = Column(String, nullable=True)
    university_degree = Column(String)  # Not making it required
    current_company = Column(String, nullable=True)
    skills = Column(MutableList.as_mutable(JSON), default=[])
    strengths = Column(MutableDict.as_mutable(JSON), default={})
    weaknesses = Column(MutableDict.as_mutable(JSON), default={})
    car_companies_associated = relationship(
        "Make", secondary=make_person_association, back_populates="key_personnel"
    )
    founded_companies = relationship(
        "Make", secondary=make_founders_association, back_populates="founders"
    )

    companies_as_ceo = relationship(
        "Make", secondary=make_ceo_association, back_populates="ceos"
    )
