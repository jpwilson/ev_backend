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


class CarUpdate(BaseModel):
    make_id: Optional[int] = Field(None)
    model: Optional[str] = Field(None)
    submodel: Optional[str] = Field(None)
    generation: Optional[str] = Field(None)
    image_url: Optional[str] = Field(None)
    acceleration_0_60: Optional[float] = Field(None)
    current_price: Optional[float] = Field(None)
    epa_range: Optional[float] = Field(None)
    number_of_full_adult_seats: Optional[int] = Field(None)
    available_countries: Optional[Dict[str, List[str]]] = Field(None)
    battery_capacity: Optional[float] = Field(None)
    battery_max_charging_speed: Optional[float] = Field(None)
    bidirectional_details: Optional[Dict[str, str]] = Field(None)
    chargers: Optional[List[str]] = Field(None)
    carmodel_first_released: Optional[str] = Field(None)
    carmodel_ended: Optional[str] = Field(None)
    trim_first_released: Optional[str] = Field(None)
    trim_ended: Optional[str] = Field(None)
    color_options: Optional[Dict[str, List[str]]] = Field(None)
    customer_and_critic_rating: Optional[Dict[str, float]] = Field(None)
    drive_assist_features: Optional[List[str]] = Field(None)
    drive_type: Optional[str] = Field(None)
    frunk_capacity: Optional[float] = Field(None)
    has_spare_tire: Optional[bool] = Field(None)
    power: Optional[float] = Field(None)
    top_speed: Optional[float] = Field(None)
    torque: Optional[float] = Field(None)
    speed_acc: Optional[Dict[str, float]] = Field(None)
    price_history: Optional[Dict[str, float]] = Field(None)
    range_details: Optional[Dict[str, float]] = Field(None)
    reviews: List[Review] = Field(None)
    euroncap_rating: Optional[float] = Field(None)
    nhtsa_rating: Optional[float] = Field(None)
    sentry_security: Optional[bool] = Field(None)
    sentry_details: Optional[Dict[str, str]] = Field(None)
    camping_features: Optional[Dict[str, str]] = Field(None)
    dog_mode: Optional[Dict[str, str]] = Field(None)
    infotainment_details: Optional[Dict[str, str]] = Field(None)
    interior_ambient_lighting_details: Optional[Dict[str, str]] = Field(None)
    keyless: Optional[bool] = Field(None)
    number_of_passenger_doors: Optional[int] = Field(None)
    remote_heating_cooling: Optional[Dict[str, str]] = Field(None)
    seating_details: Optional[Dict[str, str]] = Field(None)
    towing_details: Optional[Dict[str, str]] = Field(None)
    regen_details: Optional[Dict[str, str]] = Field(None)
    vehicle_class: Optional[str] = Field(None)
    vehicle_sound_details: Optional[Dict[str, str]] = Field(None)


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
