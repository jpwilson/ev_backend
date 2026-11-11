"""Catalog hierarchy: makes -> models -> generations -> cars (variants) -> variant_markets.

Additive only. Legacy columns are never altered; legacy endpoints keep their
response shapes. Seed-owned values that would collide with a legacy column live
in new columns (makes.catalog_*, cars.variant_name / battery_kwh / ...), so the
catalog loader never has to write a column that a legacy endpoint reads. See
docs/catalog-api.md and eeveecars/docs/catalog-design.md sections 3.2 and 7.2.

Differences from the design doc's DDL sketch (director's brief wins):
- makes: catalog_* copies of name/status/status_details/description/country/
  headquarters/website_url + founded, parent_group; status_date is text
  ('YYYY', 'YYYY-MM' or 'YYYY-MM-DD') so partial dates keep their precision.
- cars: variant spec columns named as in the seed (battery_kwh, power_hp, ...)
  instead of reusing legacy battery_capacity/power/...; catalog_updated_at
  drives sitemap lastmod.
- makes / models / cars: catalog_origin = 'seed' marks rows the loader inserted,
  so the downgrade can remove exactly those rows.
- images: sourced from Wikimedia Commons / press / reviewed legacy files
  (source, file_url, page_url, credit, license, view, verified) instead of the
  storage-bucket pipeline of section 7.2.
- model_markets.launch_date / end_date are partial-date text, basis gains 'seed'.
- change_proposals extensions (section 3.2) are left for the research-pipeline PR.

Revision ID: catalog_02_hierarchy
Revises: catalog_01_adopt_002_003
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "catalog_02_hierarchy"
down_revision: Union[str, None] = "catalog_01_adopt_002_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LIFECYCLE = "('upcoming','current','discontinued','cancelled')"
MARKETS = "('US','CA','EU','UK','CN','JP','KR','IN','AU')"
BODY = "('sedan','hatchback','wagon','coupe','convertible','suv','pickup','van','minivan','microcar')"
PARTIAL_DATE = r"'^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'"
SLUG = r"'^[a-z0-9]+(-[a-z0-9]+)*$'"

UPGRADE = [
    # ------------------------------------------------------------ makes
    "ALTER TABLE makes ADD COLUMN slug text",
    "ALTER TABLE makes ADD COLUMN status_date text",
    "ALTER TABLE makes ADD COLUMN founded smallint",
    "ALTER TABLE makes ADD COLUMN parent_group text",
    "ALTER TABLE makes ADD COLUMN external_ids jsonb NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE makes ADD COLUMN catalog_name text",
    "ALTER TABLE makes ADD COLUMN catalog_status text",
    "ALTER TABLE makes ADD COLUMN catalog_status_details text",
    "ALTER TABLE makes ADD COLUMN catalog_description text",
    "ALTER TABLE makes ADD COLUMN catalog_country text",
    "ALTER TABLE makes ADD COLUMN catalog_headquarters text",
    "ALTER TABLE makes ADD COLUMN catalog_website_url text",
    "ALTER TABLE makes ADD COLUMN catalog_updated_at timestamptz",
    "ALTER TABLE makes ADD COLUMN catalog_origin text CHECK (catalog_origin IN ('seed'))",
    f"ALTER TABLE makes ADD CONSTRAINT makes_slug_chk CHECK (slug IS NULL OR slug ~ {SLUG})",
    "ALTER TABLE makes ADD CONSTRAINT makes_catalog_status_chk CHECK (catalog_status IS NULL OR "
    "catalog_status IN ('active','pre-production','defunct','acquired'))",
    f"ALTER TABLE makes ADD CONSTRAINT makes_status_date_chk CHECK (status_date IS NULL OR status_date ~ {PARTIAL_DATE})",
    "CREATE UNIQUE INDEX makes_slug_uq ON makes (slug)",
    # ------------------------------------------------------------ models (002)
    "ALTER TABLE models DROP CONSTRAINT IF EXISTS models_status_check",
    "UPDATE models SET status = CASE status WHEN 'in_production' THEN 'current' "
    "WHEN 'announced' THEN 'upcoming' WHEN 'pre_order' THEN 'upcoming' ELSE status END",
    "ALTER TABLE models ALTER COLUMN status SET DEFAULT 'current'",
    f"ALTER TABLE models ADD CONSTRAINT models_status_chk CHECK (status IN {LIFECYCLE})",
    "ALTER TABLE models ADD COLUMN url_slug text",
    "ALTER TABLE models ADD COLUMN aliases text[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE models ADD COLUMN is_commercial boolean NOT NULL DEFAULT false",
    "ALTER TABLE models ADD COLUMN external_ids jsonb NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE models ADD COLUMN catalog_origin text CHECK (catalog_origin IN ('seed'))",
    f"ALTER TABLE models ADD CONSTRAINT models_url_slug_chk CHECK (url_slug IS NULL OR (url_slug ~ {SLUG} "
    "AND url_slug !~ '^[0-9]+$' AND position('-vs-' in url_slug) = 0))",
    f"ALTER TABLE models ADD CONSTRAINT models_body_style_chk CHECK (url_slug IS NULL OR body_style IS NULL OR body_style IN {BODY})",
    "CREATE UNIQUE INDEX models_make_url_slug_uq ON models (make_id, url_slug)",
    # ------------------------------------------------------------ generations
    f"""CREATE TABLE generations (
  id               serial PRIMARY KEY,
  model_id         int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  slug             text NOT NULL CHECK (slug ~ '^[0-9]{{4}}(-[a-z0-9]+)*$'),
  name             text NOT NULL,
  kind             text NOT NULL CHECK (kind IN ('generation','refresh')),
  ordinal          smallint,
  code_name        text,
  marketed_name    text,
  platform         text,
  start_year       smallint,
  end_year         smallint,
  status           text NOT NULL CHECK (status IN {LIFECYCLE}),
  description      text,
  sources          jsonb NOT NULL DEFAULT '[]'::jsonb,
  last_verified_at timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_id, slug)
)""",
    # ------------------------------------------------------------ cars = variants
    "ALTER TABLE cars ADD COLUMN generation_id int REFERENCES generations(id) ON DELETE SET NULL",
    "ALTER TABLE cars ADD COLUMN variant_slug text",
    "ALTER TABLE cars ADD COLUMN variant_name text",
    f"ALTER TABLE cars ADD COLUMN status text CHECK (status IN {LIFECYCLE})",
    "ALTER TABLE cars ADD COLUMN year_from smallint",
    "ALTER TABLE cars ADD COLUMN year_to smallint",
    "ALTER TABLE cars ADD COLUMN drivetrain text CHECK (drivetrain IN ('FWD','RWD','AWD'))",
    f"ALTER TABLE cars ADD COLUMN body_type text CHECK (body_type IN {BODY})",
    "ALTER TABLE cars ADD COLUMN seats smallint",
    "ALTER TABLE cars ADD COLUMN battery_kwh double precision",
    "ALTER TABLE cars ADD COLUMN battery_basis text CHECK (battery_basis IN ('usable','gross'))",
    "ALTER TABLE cars ADD COLUMN power_hp double precision",
    "ALTER TABLE cars ADD COLUMN torque_lbft double precision",
    "ALTER TABLE cars ADD COLUMN accel_0_60_s double precision",
    "ALTER TABLE cars ADD COLUMN accel_0_100_s double precision",
    "ALTER TABLE cars ADD COLUMN top_speed_mph double precision",
    "ALTER TABLE cars ADD COLUMN dc_kw double precision",
    "ALTER TABLE cars ADD COLUMN variant_order smallint",
    "ALTER TABLE cars ADD COLUMN catalog_origin text CHECK (catalog_origin IN ('seed'))",
    "ALTER TABLE cars ADD COLUMN catalog_updated_at timestamptz",
    f"ALTER TABLE cars ADD CONSTRAINT cars_variant_slug_chk CHECK (variant_slug IS NULL OR variant_slug ~ {SLUG})",
    "CREATE UNIQUE INDEX cars_generation_variant_uq ON cars (generation_id, variant_slug)",
    "CREATE INDEX idx_cars_generation_id ON cars (generation_id)",
    # ------------------------------------------------------------ model_markets
    f"""CREATE TABLE model_markets (
  model_id         int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  market           text NOT NULL CHECK (market IN {MARKETS}),
  status           text NOT NULL CHECK (status IN {LIFECYCLE}),
  local_name       text,
  launch_date      text CHECK (launch_date IS NULL OR launch_date ~ {PARTIAL_DATE}),
  end_date         text CHECK (end_date IS NULL OR end_date ~ {PARTIAL_DATE}),
  basis            text NOT NULL DEFAULT 'seed' CHECK (basis IN ('sourced','legacy','seed')),
  sources          jsonb NOT NULL DEFAULT '[]'::jsonb,
  last_verified_at timestamptz,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (model_id, market),
  CHECK (basis <> 'sourced' OR jsonb_array_length(sources) > 0)
)""",
    # ------------------------------------------------------------ variant_markets
    f"""CREATE TABLE variant_markets (
  id                serial PRIMARY KEY,
  car_id            int  NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  market            text NOT NULL CHECK (market IN {MARKETS}),
  model_year        smallint,
  currency          char(3),
  launch_price      numeric(12,2),
  launch_price_date date,
  current_price     numeric(12,2),
  price_basis       text CHECK (price_basis IN ('msrp_excl_destination','msrp_incl_destination','list_incl_vat')),
  range_value       numeric(6,1),
  range_unit        text CHECK (range_unit IN ('mi','km')),
  range_cycle       text CHECK (range_cycle IN ('EPA','WLTP','CLTC','WLTC','KR','MIDC')),
  connector         text CHECK (connector IN ('NACS','CCS1','CCS2','GBT','CHADEMO')),
  is_estimate       boolean NOT NULL DEFAULT false,
  external_ids      jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  sources           jsonb NOT NULL DEFAULT '[]'::jsonb,
  last_verified_at  timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (range_value IS NULL OR (range_unit IS NOT NULL AND range_cycle IS NOT NULL)),
  CHECK (coalesce(launch_price, current_price) IS NULL OR (currency IS NOT NULL AND price_basis IS NOT NULL))
)""",
    "CREATE UNIQUE INDEX variant_markets_uq ON variant_markets (car_id, market, coalesce(model_year, 0))",
    # ------------------------------------------------------------ model_relations
    """CREATE TABLE model_relations (
  model_id         int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  related_model_id int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  relation         text NOT NULL CHECK (relation IN ('twin','successor')),
  sources          jsonb NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (model_id, related_model_id, relation),
  CHECK (model_id <> related_model_id)
)""",
    # ------------------------------------------------------------ url_redirects
    """CREATE TABLE url_redirects (
  old_path    text PRIMARY KEY,
  entity_type text NOT NULL CHECK (entity_type IN ('make','model','generation','variant')),
  entity_id   int  NOT NULL,
  reason      text NOT NULL CHECK (reason IN ('legacy','rename','merge','alias')),
  created_at  timestamptz NOT NULL DEFAULT now()
)""",
    # ------------------------------------------------------------ images
    """CREATE TABLE images (
  id            serial PRIMARY KEY,
  model_id      int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  generation_id int  REFERENCES generations(id) ON DELETE CASCADE,
  variant_id    int  REFERENCES cars(id) ON DELETE SET NULL,
  source        text NOT NULL CHECK (source IN ('commons','press','legacy')),
  file_url      text NOT NULL,
  page_url      text,
  credit        text,
  license       text,
  view          text CHECK (view IN ('front_3q','rear_3q','side','front','rear','interior','dashboard','detail')),
  verified      boolean NOT NULL DEFAULT false,
  is_primary    boolean NOT NULL DEFAULT false,
  sort_order    smallint NOT NULL DEFAULT 0,
  alt_text      text,
  width         int,
  height        int,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (source = 'legacy' OR (credit IS NOT NULL AND page_url IS NOT NULL)),
  UNIQUE (generation_id, file_url)
)""",
    "CREATE UNIQUE INDEX images_primary_uq ON images (generation_id) WHERE is_primary",
    "CREATE INDEX idx_images_model_id ON images (model_id)",
    # ------------------------------------------------------------ RLS (no anon policies)
    "ALTER TABLE generations ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE model_markets ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE variant_markets ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE model_relations ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE url_redirects ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE images ENABLE ROW LEVEL SECURITY",
]

CARS_NEW_COLUMNS = [
    "generation_id", "variant_slug", "variant_name", "status", "year_from", "year_to",
    "drivetrain", "body_type", "seats", "battery_kwh", "battery_basis", "power_hp",
    "torque_lbft", "accel_0_60_s", "accel_0_100_s", "top_speed_mph", "dc_kw",
    "variant_order", "catalog_origin", "catalog_updated_at",
]
MAKES_NEW_COLUMNS = [
    "slug", "status_date", "founded", "parent_group", "external_ids", "catalog_name",
    "catalog_status", "catalog_status_details", "catalog_description", "catalog_country",
    "catalog_headquarters", "catalog_website_url", "catalog_updated_at", "catalog_origin",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS images",
    "DROP TABLE IF EXISTS url_redirects",
    "DROP TABLE IF EXISTS model_relations",
    "DROP TABLE IF EXISTS variant_markets",
    "DROP TABLE IF EXISTS model_markets",
    # Rows the loader inserted into cars exist only for the catalog; remove them
    # before their columns go (legacy rows have catalog_origin NULL).
    "DELETE FROM cars WHERE catalog_origin = 'seed'",
    "DROP INDEX IF EXISTS cars_generation_variant_uq",
    "DROP INDEX IF EXISTS idx_cars_generation_id",
    "ALTER TABLE cars DROP CONSTRAINT IF EXISTS cars_variant_slug_chk",
    *["ALTER TABLE cars DROP COLUMN IF EXISTS %s" % c for c in CARS_NEW_COLUMNS],
    "DROP TABLE IF EXISTS generations",
    # Models and makes the loader inserted (002-backfilled and legacy rows have
    # catalog_origin NULL and are kept).
    "UPDATE cars SET model_id = NULL WHERE model_id IN (SELECT id FROM models WHERE catalog_origin = 'seed')",
    "DELETE FROM models WHERE catalog_origin = 'seed'",
    "ALTER TABLE models DROP COLUMN IF EXISTS catalog_origin",
    "DROP INDEX IF EXISTS models_make_url_slug_uq",
    "ALTER TABLE models DROP CONSTRAINT IF EXISTS models_body_style_chk",
    "ALTER TABLE models DROP CONSTRAINT IF EXISTS models_url_slug_chk",
    "ALTER TABLE models DROP COLUMN IF EXISTS url_slug",
    "ALTER TABLE models DROP COLUMN IF EXISTS aliases",
    "ALTER TABLE models DROP COLUMN IF EXISTS is_commercial",
    "ALTER TABLE models DROP COLUMN IF EXISTS external_ids",
    "ALTER TABLE models DROP CONSTRAINT IF EXISTS models_status_chk",
    # Lossy by design: 'pre_order' cannot be told apart from 'announced' any more.
    "UPDATE models SET status = CASE status WHEN 'current' THEN 'in_production' "
    "WHEN 'upcoming' THEN 'announced' ELSE status END",
    "ALTER TABLE models ALTER COLUMN status SET DEFAULT 'in_production'",
    "ALTER TABLE models ADD CONSTRAINT models_status_check CHECK (status IN "
    "('announced','pre_order','in_production','discontinued','cancelled'))",
    "DROP INDEX IF EXISTS makes_slug_uq",
    "ALTER TABLE makes DROP CONSTRAINT IF EXISTS makes_slug_chk",
    "ALTER TABLE makes DROP CONSTRAINT IF EXISTS makes_catalog_status_chk",
    "ALTER TABLE makes DROP CONSTRAINT IF EXISTS makes_status_date_chk",
    "DELETE FROM makes WHERE catalog_origin = 'seed'",
    *["ALTER TABLE makes DROP COLUMN IF EXISTS %s" % c for c in MAKES_NEW_COLUMNS],
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
