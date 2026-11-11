"""SQLAlchemy Core tables for the catalog (Alembic catalog_02_hierarchy).

Deliberately a SEPARATE MetaData from database.Base: the legacy ORM classes
(Car, Make, VehicleModel) must not learn the new columns, otherwise every legacy
query would select columns that do not exist until the migration has run.
Only /catalog/* and scripts/catalog/* use these definitions.
Foreign keys are declared in the migration, not here (nothing below emits DDL).
"""
from sqlalchemy import (
    ARRAY, JSON, Boolean, Column, Date, DateTime, Float, Integer, MetaData, Numeric,
    SmallInteger, String, Table, Text,
)
from sqlalchemy.dialects.postgresql import JSONB

catalog_metadata = MetaData()

makes = Table(
    "makes", catalog_metadata,
    Column("id", Integer, primary_key=True),
    # legacy columns (read; written only for rows the loader creates)
    Column("name", String), Column("status", String), Column("status_details", Text),
    Column("description", Text), Column("website_url", String), Column("country", String),
    Column("headquarters", String), Column("founding_date", String),
    Column("lrg_logo_img_url", String), Column("unionized", Boolean),
    Column("updated_at", DateTime),
    # 002
    Column("sources", JSONB), Column("last_verified_at", DateTime(timezone=True)),
    # catalog_02
    Column("slug", Text), Column("status_date", Text), Column("founded", SmallInteger),
    Column("parent_group", Text), Column("external_ids", JSONB),
    Column("catalog_name", Text), Column("catalog_status", Text),
    Column("catalog_status_details", Text), Column("catalog_description", Text),
    Column("catalog_country", Text), Column("catalog_headquarters", Text),
    Column("catalog_website_url", Text), Column("catalog_updated_at", DateTime(timezone=True)),
    Column("catalog_origin", Text),
)

models = Table(
    "models", catalog_metadata,
    Column("id", Integer, primary_key=True),
    Column("make_id", Integer), Column("name", Text), Column("slug", Text),
    Column("body_style", Text), Column("status", Text), Column("description", Text),
    Column("official_url", Text), Column("sources", JSONB),
    Column("last_verified_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)), Column("updated_at", DateTime(timezone=True)),
    Column("url_slug", Text), Column("aliases", ARRAY(Text)), Column("is_commercial", Boolean),
    Column("external_ids", JSONB), Column("catalog_origin", Text),
)

generations = Table(
    "generations", catalog_metadata,
    Column("id", Integer, primary_key=True),
    Column("model_id", Integer), Column("slug", Text), Column("name", Text), Column("kind", Text),
    Column("ordinal", SmallInteger), Column("code_name", Text), Column("marketed_name", Text),
    Column("platform", Text), Column("start_year", SmallInteger), Column("end_year", SmallInteger),
    Column("status", Text), Column("description", Text), Column("sources", JSONB),
    Column("last_verified_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)), Column("updated_at", DateTime(timezone=True)),
)

# cars = variants. Legacy columns listed are the ones the loader fills for rows it creates.
cars = Table(
    "cars", catalog_metadata,
    Column("id", Integer, primary_key=True),
    Column("make_id", Integer), Column("make_name", String), Column("model", String),
    Column("submodel", String), Column("generation", String), Column("image_url", String),
    Column("acceleration_0_60", Float), Column("current_price", Float), Column("epa_range", Float),
    Column("number_of_full_adult_seats", Integer), Column("full_slug", String),
    Column("make_model_slug", String), Column("is_model_rep", Boolean),
    Column("model_webpage", String), Column("production_availability", Boolean),
    Column("availability_desc", String), Column("battery_capacity", Float),
    Column("battery_max_charging_speed", Float), Column("drive_type", String),
    Column("power", Float), Column("top_speed", Float), Column("torque", Float),
    Column("vehicle_class", String), Column("model_description", Text),
    Column("updated_at", DateTime),
    # Legacy json (not jsonb) columns: rows the loader creates get the ORM defaults so CarRead validates
    Column("available_countries", JSON), Column("bidirectional_details", JSON),
    Column("chargers", JSON), Column("color_options", JSON),
    Column("customer_and_critic_rating", JSON), Column("drive_assist_features", JSON),
    Column("speed_acc", JSON), Column("price_history", JSON), Column("reviews", JSON),
    Column("range_details", JSON), Column("sentry_details", JSON),
    Column("camping_features", JSON), Column("dog_mode", JSON),
    Column("infotainment_details", JSON), Column("interior_ambient_lighting_details", JSON),
    Column("remote_heating_cooling", JSON), Column("seating_details", JSON),
    Column("towing_details", JSON), Column("regen_details", JSON),
    Column("vehicle_sound_details", JSON), Column("images", JSONB),
    # 002
    Column("model_id", Integer), Column("sources", JSONB),
    Column("last_verified_at", DateTime(timezone=True)),
    # catalog_02
    Column("generation_id", Integer), Column("variant_slug", Text), Column("variant_name", Text),
    Column("status", Text), Column("year_from", SmallInteger), Column("year_to", SmallInteger),
    Column("drivetrain", Text), Column("body_type", Text), Column("seats", SmallInteger),
    Column("battery_kwh", Float), Column("battery_basis", Text), Column("power_hp", Float),
    Column("torque_lbft", Float), Column("accel_0_60_s", Float), Column("accel_0_100_s", Float),
    Column("top_speed_mph", Float), Column("dc_kw", Float), Column("variant_order", SmallInteger), Column("catalog_origin", Text),
    Column("catalog_updated_at", DateTime(timezone=True)),
)

model_markets = Table(
    "model_markets", catalog_metadata,
    Column("model_id", Integer, primary_key=True), Column("market", Text, primary_key=True),
    Column("status", Text), Column("local_name", Text), Column("launch_date", Text),
    Column("end_date", Text), Column("basis", Text), Column("sources", JSONB),
    Column("last_verified_at", DateTime(timezone=True)), Column("updated_at", DateTime(timezone=True)),
)

variant_markets = Table(
    "variant_markets", catalog_metadata,
    Column("id", Integer, primary_key=True),
    Column("car_id", Integer), Column("market", Text), Column("model_year", SmallInteger),
    Column("currency", String(3)), Column("launch_price", Numeric(12, 2)),
    Column("launch_price_date", Date), Column("current_price", Numeric(12, 2)),
    Column("price_basis", Text), Column("range_value", Numeric(6, 1)), Column("range_unit", Text),
    Column("range_cycle", Text), Column("connector", Text), Column("is_estimate", Boolean),
    Column("external_ids", JSONB), Column("sources", JSONB),
    Column("last_verified_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)), Column("updated_at", DateTime(timezone=True)),
)

model_relations = Table(
    "model_relations", catalog_metadata,
    Column("model_id", Integer, primary_key=True),
    Column("related_model_id", Integer, primary_key=True),
    Column("relation", Text, primary_key=True), Column("sources", JSONB),
)

url_redirects = Table(
    "url_redirects", catalog_metadata,
    Column("old_path", Text, primary_key=True), Column("entity_type", Text),
    Column("entity_id", Integer), Column("reason", Text),
    Column("created_at", DateTime(timezone=True)),
)

images = Table(
    "images", catalog_metadata,
    Column("id", Integer, primary_key=True),
    Column("model_id", Integer), Column("generation_id", Integer), Column("variant_id", Integer),
    Column("source", Text), Column("file_url", Text), Column("page_url", Text),
    Column("credit", Text), Column("license", Text), Column("view", Text),
    Column("verified", Boolean), Column("is_primary", Boolean), Column("sort_order", SmallInteger),
    Column("alt_text", Text), Column("width", Integer), Column("height", Integer),
    Column("created_at", DateTime(timezone=True)), Column("updated_at", DateTime(timezone=True)),
)

# Tables whose presence means catalog_02_hierarchy has been applied.
REQUIRED_TABLES = ("generations", "variant_markets", "model_markets", "images", "url_redirects")
