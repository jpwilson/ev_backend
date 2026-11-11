-- ============================================
-- 004: Catalog hierarchy (generated: alembic upgrade a3f8b2c1d4e5:catalog_02_hierarchy --sql)
-- For the Supabase SQL editor, as an alternative to running Alembic.
-- Runs in one transaction; safe whether or not 002/003 were applied (catalog_01 is IF NOT EXISTS).
-- Precondition: alembic_version = 'a3f8b2c1d4e5' (the final UPDATE matches on it).
-- Run over the direct connection (port 5432), not the transaction pooler.
-- Rollback: alembic downgrade a3f8b2c1d4e5 (or: --sql catalog_02_hierarchy:a3f8b2c1d4e5).
-- Do not edit by hand; regenerate from the Alembic revisions.
-- ============================================

BEGIN;

-- Running upgrade a3f8b2c1d4e5 -> catalog_01_adopt_002_003

CREATE TABLE IF NOT EXISTS models (
  id SERIAL PRIMARY KEY,
  make_id INTEGER REFERENCES makes(id),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  body_style TEXT,
  status TEXT NOT NULL DEFAULT 'in_production'
    CHECK (status IN ('announced','pre_order','in_production','discontinued','cancelled')),
  update_cadence TEXT NOT NULL DEFAULT 'model_year'
    CHECK (update_cadence IN ('continuous','model_year','irregular')),
  announced_date DATE,
  launch_date DATE,
  discontinued_date DATE,
  description TEXT,
  official_url TEXT,
  popularity_rank INTEGER,
  last_verified_at TIMESTAMPTZ,
  sources JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE cars ADD COLUMN IF NOT EXISTS model_id INTEGER REFERENCES models(id);

ALTER TABLE cars ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;

ALTER TABLE cars ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE makes ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;

ALTER TABLE makes ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE makes ADD COLUMN IF NOT EXISTS update_cadence TEXT NOT NULL DEFAULT 'model_year'
  CHECK (update_cadence IN ('continuous','model_year','irregular'));

CREATE INDEX IF NOT EXISTS idx_models_make_id ON models(make_id);

CREATE INDEX IF NOT EXISTS idx_cars_model_id ON cars(model_id);

CREATE TABLE IF NOT EXISTS crawl_runs (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running','completed','failed')),
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS change_proposals (
  id BIGSERIAL PRIMARY KEY,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('car','make','model')),
  entity_id INTEGER NOT NULL,
  field TEXT NOT NULL,
  old_value JSONB,
  new_value JSONB,
  source_name TEXT,
  source_url TEXT,
  confidence REAL,
  rationale TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected','auto_applied')),
  crawl_run_id BIGINT REFERENCES crawl_runs(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  applied_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_change_proposals_status ON change_proposals(status, created_at);

CREATE INDEX IF NOT EXISTS idx_change_proposals_entity ON change_proposals(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS price_snapshots (
  id BIGSERIAL PRIMARY KEY,
  car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  market TEXT NOT NULL DEFAULT 'US',
  currency TEXT NOT NULL DEFAULT 'USD',
  msrp NUMERIC(12,2),
  effective_price NUMERIC(12,2),
  source_url TEXT,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_car ON price_snapshots(car_id, captured_at DESC);

ALTER TABLE models ENABLE ROW LEVEL SECURITY;

ALTER TABLE crawl_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE change_proposals ENABLE ROW LEVEL SECURITY;

ALTER TABLE price_snapshots ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='catalog_01_adopt_002_003' WHERE alembic_version.version_num = 'a3f8b2c1d4e5';

-- Running upgrade catalog_01_adopt_002_003 -> catalog_02_hierarchy

ALTER TABLE makes ADD COLUMN slug text;

ALTER TABLE makes ADD COLUMN status_date text;

ALTER TABLE makes ADD COLUMN founded smallint;

ALTER TABLE makes ADD COLUMN parent_group text;

ALTER TABLE makes ADD COLUMN external_ids jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE makes ADD COLUMN catalog_name text;

ALTER TABLE makes ADD COLUMN catalog_status text;

ALTER TABLE makes ADD COLUMN catalog_status_details text;

ALTER TABLE makes ADD COLUMN catalog_description text;

ALTER TABLE makes ADD COLUMN catalog_country text;

ALTER TABLE makes ADD COLUMN catalog_headquarters text;

ALTER TABLE makes ADD COLUMN catalog_website_url text;

ALTER TABLE makes ADD COLUMN catalog_updated_at timestamptz;

ALTER TABLE makes ADD COLUMN catalog_origin text CHECK (catalog_origin IN ('seed'));

ALTER TABLE makes ADD CONSTRAINT makes_slug_chk CHECK (slug IS NULL OR slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$');

ALTER TABLE makes ADD CONSTRAINT makes_catalog_status_chk CHECK (catalog_status IS NULL OR catalog_status IN ('active','pre-production','defunct','acquired'));

ALTER TABLE makes ADD CONSTRAINT makes_status_date_chk CHECK (status_date IS NULL OR status_date ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$');

CREATE UNIQUE INDEX makes_slug_uq ON makes (slug);

ALTER TABLE models DROP CONSTRAINT IF EXISTS models_status_check;

UPDATE models SET status = CASE status WHEN 'in_production' THEN 'current' WHEN 'announced' THEN 'upcoming' WHEN 'pre_order' THEN 'upcoming' ELSE status END;

ALTER TABLE models ALTER COLUMN status SET DEFAULT 'current';

ALTER TABLE models ADD CONSTRAINT models_status_chk CHECK (status IN ('upcoming','current','discontinued','cancelled'));

ALTER TABLE models ADD COLUMN url_slug text;

ALTER TABLE models ADD COLUMN aliases text[] NOT NULL DEFAULT '{}';

ALTER TABLE models ADD COLUMN is_commercial boolean NOT NULL DEFAULT false;

ALTER TABLE models ADD COLUMN external_ids jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE models ADD COLUMN catalog_origin text CHECK (catalog_origin IN ('seed'));

ALTER TABLE models ADD CONSTRAINT models_url_slug_chk CHECK (url_slug IS NULL OR (url_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND url_slug !~ '^[0-9]+$' AND position('-vs-' in url_slug) = 0));

ALTER TABLE models ADD CONSTRAINT models_body_style_chk CHECK (url_slug IS NULL OR body_style IS NULL OR body_style IN ('sedan','hatchback','wagon','coupe','convertible','suv','pickup','van','minivan','microcar'));

CREATE UNIQUE INDEX models_make_url_slug_uq ON models (make_id, url_slug);

CREATE TABLE generations (
  id               serial PRIMARY KEY,
  model_id         int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  slug             text NOT NULL CHECK (slug ~ '^[0-9]{4}(-[a-z0-9]+)*$'),
  name             text NOT NULL,
  kind             text NOT NULL CHECK (kind IN ('generation','refresh')),
  ordinal          smallint,
  code_name        text,
  marketed_name    text,
  platform         text,
  start_year       smallint,
  end_year         smallint,
  status           text NOT NULL CHECK (status IN ('upcoming','current','discontinued','cancelled')),
  description      text,
  sources          jsonb NOT NULL DEFAULT '[]'::jsonb,
  last_verified_at timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_id, slug)
);

ALTER TABLE cars ADD COLUMN generation_id int REFERENCES generations(id) ON DELETE SET NULL;

ALTER TABLE cars ADD COLUMN variant_slug text;

ALTER TABLE cars ADD COLUMN variant_name text;

ALTER TABLE cars ADD COLUMN status text CHECK (status IN ('upcoming','current','discontinued','cancelled'));

ALTER TABLE cars ADD COLUMN year_from smallint;

ALTER TABLE cars ADD COLUMN year_to smallint;

ALTER TABLE cars ADD COLUMN drivetrain text CHECK (drivetrain IN ('FWD','RWD','AWD'));

ALTER TABLE cars ADD COLUMN body_type text CHECK (body_type IN ('sedan','hatchback','wagon','coupe','convertible','suv','pickup','van','minivan','microcar'));

ALTER TABLE cars ADD COLUMN seats smallint;

ALTER TABLE cars ADD COLUMN battery_kwh double precision;

ALTER TABLE cars ADD COLUMN battery_basis text CHECK (battery_basis IN ('usable','gross'));

ALTER TABLE cars ADD COLUMN power_hp double precision;

ALTER TABLE cars ADD COLUMN torque_lbft double precision;

ALTER TABLE cars ADD COLUMN accel_0_60_s double precision;

ALTER TABLE cars ADD COLUMN accel_0_100_s double precision;

ALTER TABLE cars ADD COLUMN top_speed_mph double precision;

ALTER TABLE cars ADD COLUMN dc_kw double precision;

ALTER TABLE cars ADD COLUMN variant_order smallint;

ALTER TABLE cars ADD COLUMN catalog_origin text CHECK (catalog_origin IN ('seed'));

ALTER TABLE cars ADD COLUMN catalog_updated_at timestamptz;

ALTER TABLE cars ADD CONSTRAINT cars_variant_slug_chk CHECK (variant_slug IS NULL OR variant_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$');

CREATE UNIQUE INDEX cars_generation_variant_uq ON cars (generation_id, variant_slug);

CREATE INDEX idx_cars_generation_id ON cars (generation_id);

CREATE TABLE model_markets (
  model_id         int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  market           text NOT NULL CHECK (market IN ('US','CA','EU','UK','CN','JP','KR','IN','AU')),
  status           text NOT NULL CHECK (status IN ('upcoming','current','discontinued','cancelled')),
  local_name       text,
  launch_date      text CHECK (launch_date IS NULL OR launch_date ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
  end_date         text CHECK (end_date IS NULL OR end_date ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'),
  basis            text NOT NULL DEFAULT 'seed' CHECK (basis IN ('sourced','legacy','seed')),
  sources          jsonb NOT NULL DEFAULT '[]'::jsonb,
  last_verified_at timestamptz,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (model_id, market),
  CHECK (basis <> 'sourced' OR jsonb_array_length(sources) > 0)
);

CREATE TABLE variant_markets (
  id                serial PRIMARY KEY,
  car_id            int  NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  market            text NOT NULL CHECK (market IN ('US','CA','EU','UK','CN','JP','KR','IN','AU')),
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
  external_ids      jsonb NOT NULL DEFAULT '{}'::jsonb,
  sources           jsonb NOT NULL DEFAULT '[]'::jsonb,
  last_verified_at  timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (range_value IS NULL OR (range_unit IS NOT NULL AND range_cycle IS NOT NULL)),
  CHECK (coalesce(launch_price, current_price) IS NULL OR (currency IS NOT NULL AND price_basis IS NOT NULL))
);

CREATE UNIQUE INDEX variant_markets_uq ON variant_markets (car_id, market, coalesce(model_year, 0));

CREATE TABLE model_relations (
  model_id         int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  related_model_id int  NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  relation         text NOT NULL CHECK (relation IN ('twin','successor')),
  sources          jsonb NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (model_id, related_model_id, relation),
  CHECK (model_id <> related_model_id)
);

CREATE TABLE url_redirects (
  old_path    text PRIMARY KEY,
  entity_type text NOT NULL CHECK (entity_type IN ('make','model','generation','variant')),
  entity_id   int  NOT NULL,
  reason      text NOT NULL CHECK (reason IN ('legacy','rename','merge','alias')),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE images (
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
);

CREATE UNIQUE INDEX images_primary_uq ON images (generation_id) WHERE is_primary;

CREATE INDEX idx_images_model_id ON images (model_id);

ALTER TABLE generations ENABLE ROW LEVEL SECURITY;

ALTER TABLE model_markets ENABLE ROW LEVEL SECURITY;

ALTER TABLE variant_markets ENABLE ROW LEVEL SECURITY;

ALTER TABLE model_relations ENABLE ROW LEVEL SECURITY;

ALTER TABLE url_redirects ENABLE ROW LEVEL SECURITY;

ALTER TABLE images ENABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='catalog_02_hierarchy' WHERE alembic_version.version_num = 'catalog_01_adopt_002_003';

COMMIT;

