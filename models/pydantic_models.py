from typing import Dict, List, Optional

from pydantic import BaseModel, Field


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
        from_attributes = True


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
        from_attributes = True
