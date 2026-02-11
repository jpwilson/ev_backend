from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field


class Review(BaseModel):
    description: str
    url: str  # HttpUrl
    media_type: Optional[str] = None
    reviewer_id: Optional[int] = None


class StrengthWeaknessItem(BaseModel):
    score: float
    description: str


class CEOAssociationBase(BaseModel):
    person_id: int
    start_date: Optional[date] = Field(
        None, description="The start date of the CEO tenure"
    )
    end_date: Optional[date] = Field(None, description="The end date of the CEO tenure")


# For creating a new CEO association
class CEOAssociationCreate(CEOAssociationBase):
    pass


# For reading an existing CEO association, including the association ID
class CEOAssociationRead(CEOAssociationBase):
    id: int


class Role(BaseModel):
    title: str
    company: str


class PersonBase(BaseModel):
    name: str
    age: Optional[int]
    location: Optional[str] = None
    university_degree: Optional[str] = None
    current_company: Optional[str] = None
    skills: Optional[List[str]] = None
    strengths: Optional[Dict[str, StrengthWeaknessItem]] = Field(default_factory=dict)
    weaknesses: Optional[Dict[str, StrengthWeaknessItem]] = Field(default_factory=dict)
    current_roles: List[Role] = Field(default_factory=list)
    previous_roles: List[Role] = Field(default_factory=list)


class PersonCreate(PersonBase):
    pass


class PersonRead(PersonBase):
    id: int


class Person(PersonBase):
    id: int

    class Config:
        from_attributes = True


class MakeBase(BaseModel):
    name: Optional[str] = Field(None)
    ceo_id: Optional[int] = Field(None)
    ceo_pay: Optional[float] = Field(None)
    headquarters: Optional[str] = Field(None)
    founding_date: Optional[str] = Field(None)
    market_cap: Optional[float] = Field(None)
    revenue: Optional[float] = Field(None)
    num_ev_models: Optional[int] = Field(None)
    first_ev_model_date: Optional[str] = Field(None)
    unionized: Optional[bool] = Field(None)
    lrg_logo_img_url: Optional[str] = Field(None)
    status: Optional[str] = Field("active", description="active, defunct, acquired, pre-production")
    status_details: Optional[str] = Field(None, description="Details about company status")
    description: Optional[str] = Field(None, description="Company overview")
    website_url: Optional[str] = Field(None, description="Official company website")
    country: Optional[str] = Field(None, description="HQ country code (e.g., US, DE, CN)")
    updated_at: Optional[datetime] = Field(None)
    # relationship ids:
    # founder_ids: Optional[List[int]] = Field(default_factory=list)
    # ceo_ids: Optional[List[int]] = Field(default_factory=list)
    # key_personnel_ids: Optional[List[int]] = Field(default_factory=list)
    # # relationships:
    # founders: Optional[List[PersonBase]] = Field(None)
    # ceos: Optional[List[PersonBase]] = Field(None)
    # key_personnel: Optional[List[PersonBase]] = Field(None)


class MakeUpdate(BaseModel):
    name: Optional[str] = Field(None)
    ceo_id: Optional[int] = Field(None)
    ceo_pay: Optional[float] = Field(None)
    headquarters: Optional[str] = Field(None)
    founding_date: Optional[str] = Field(None)
    market_cap: Optional[float] = Field(None)
    revenue: Optional[float] = Field(None)
    num_ev_models: Optional[int] = Field(None)
    first_ev_model_date: Optional[str] = Field(None)
    unionized: Optional[bool] = Field(None)
    lrg_logo_img_url: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    status_details: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    website_url: Optional[str] = Field(None)
    country: Optional[str] = Field(None)
    # relationships
    founder_ids: Optional[List[int]] = Field(None)
    ceo_ids: Optional[List[int]] = Field(None)
    key_personnel_ids: Optional[List[int]] = Field(None)
    ceo_associations: Optional[List[CEOAssociationCreate]] = Field(
        None, description="List of CEO associations with tenure dates"
    )


class MakeCreate(MakeBase):
    pass


class MakeRead(MakeBase):
    id: int
    car_id_list: List[int] = []


class CarBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    make_id: int
    make_name: Optional[str] = None
    model: str
    submodel: Optional[str] = None
    generation: Optional[str] = None
    image_url: Optional[str] = None
    acceleration_0_60: Optional[float] = None
    current_price: Optional[float] = None
    epa_range: Optional[float] = None
    number_of_full_adult_seats: Optional[int] = None
    full_slug: Optional[str] = None
    make_model_slug: Optional[str] = None
    is_model_rep: Optional[bool] = Field(
        default=False,
        description="Indicates if the car is representative of the make and model",
    )
    model_webpage: Optional[str] = None
    car_description: Optional[str] = Field(
        default=None,  # Use None as the default for partial updates
        description="A long description of the car, like an article",
        max_length=5000,
    )

    model_description: Optional[str] = Field(
        default=None,  # Use None as the default for partial updates
        description="A long description of the car, like an article",
        max_length=5000,
    )

    production_availability: Optional[bool] = Field(
        True, description="Whether the car is currently in production"
    )
    availability_desc: Optional[str] = Field(
        None, description="Available, or deprecated, unreleased etc"
    )
    available_countries: Optional[Dict[str, List[str]]] = {}

    # charging
    battery_capacity: Optional[float] = None
    battery_max_charging_speed: Optional[float] = None  # kW
    bidirectional_details: Optional[Dict[str, str]] = {}
    chargers: Optional[List[str]] = []

    # dates
    carmodel_first_released: Optional[str] = None
    carmodel_ended: Optional[str] = None
    trim_first_released: Optional[str] = None
    trim_ended: Optional[str] = None

    color_options: Optional[Dict[str, List[str]]] = (
        {}
    )  # the year is the key + list of colors as val

    customer_and_critic_rating: Optional[Dict[str, float]] = (
        {}
    )  # dict of publication: rating

    drive_assist_features: Optional[List[str]] = None
    drive_type: Optional[str] = None
    frunk_capacity: Optional[float] = None  # cu-ft

    has_spare_tire: Optional[bool] = None

    # performance
    power: Optional[float] = None  # hp
    top_speed: Optional[float] = None  # mph
    torque: Optional[float] = None  # lb-ft
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
    images: Optional[List[str]] = []
    updated_at: Optional[datetime] = None


class CarUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    make_id: Optional[int]
    make_name: Optional[str] = Field(None)
    model: Optional[str] = Field(None)
    submodel: Optional[str] = Field(None)
    generation: Optional[str] = Field(None)
    image_url: Optional[str] = Field(None)
    acceleration_0_60: Optional[float] = Field(None)
    current_price: Optional[float] = Field(None)
    epa_range: Optional[float] = Field(None)
    number_of_full_adult_seats: Optional[int] = Field(None)

    is_model_rep: Optional[bool] = Field(
        default=None,  # Use None as the default for partial updates
        description="Indicates if the car is representative of the make and model",
    )
    model_webpage: Optional[str] = None
    car_description: Optional[str] = Field(
        default=None,  # Use None as the default for partial updates
        description="A long description of the car, like an article",
        max_length=5000,
    )

    model_description: Optional[str] = Field(
        default=None,  # Use None as the default for partial updates
        description="A long description of the car, like an article",
        max_length=5000,
    )

    availability_desc: Optional[str] = Field(
        default=None, description="eg available, unreleased, discontinued"
    )
    production_availability: Optional[bool] = Field(
        default=None, description="Whether the car is currently in production"
    )
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
    images: Optional[List[str]] = Field(None)


class CarCreate(CarBase):
    pass


class CarRead(CarBase):
    id: int
    average_rating: float
    make_id: int
    model_webpage: Optional[str] = None


class SubmodelInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    submodel: str
    image_url: Optional[str]
    current_price: float
    acceleration_0_60: float
    top_speed: int
    epa_range: int
    generation: Optional[str] = None
    availability_desc: Optional[str] = None


class MakeDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    lrg_logo_img_url: Optional[str] = None
    status: Optional[str] = None
    status_details: Optional[str] = None
    description: Optional[str] = None
    website_url: Optional[str] = None
    country: Optional[str] = None
    headquarters: Optional[str] = None
    founding_date: Optional[str] = None


class PreviousGeneration(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    generation: Optional[str] = None
    image_url: Optional[str] = None
    submodels: List[SubmodelInfo] = []


class ModelDetailResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    representative_model: CarRead
    submodels: List[SubmodelInfo]
    make_details: Optional[MakeDetails] = None
    previous_generations: List[PreviousGeneration] = []


class Car(CarBase):
    id: int

    class Config:
        from_attributes = True
