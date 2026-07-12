-- ============================================
-- 002: First-class Model entity + provenance columns
-- Run in Supabase SQL Editor (project: mesvpswjkqqogdoscyxx)
-- Additive + idempotent: safe to re-run, no breaking changes.
-- See DATA_FRESHNESS_PLAN.md for the design.
-- ============================================

-- 1. models table: the layer between makes and cars (trims).
--    "Model" previously existed only as the make_model_slug string convention.
CREATE TABLE IF NOT EXISTS public.models (
  id SERIAL PRIMARY KEY,
  make_id INTEGER REFERENCES public.makes(id),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,               -- = cars.make_model_slug
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

-- 2. Backfill from the representative car of each existing model
INSERT INTO public.models (make_id, name, slug, body_style, status, description, official_url)
SELECT
  c.make_id,
  c.model,
  c.make_model_slug,
  c.vehicle_class,
  CASE
    WHEN c.availability_desc = 'available' THEN 'in_production'
    WHEN c.availability_desc = 'discontinued' THEN 'discontinued'
    WHEN c.availability_desc ILIKE 'not yet%' OR c.availability_desc = 'unreleased' THEN 'announced'
    ELSE 'in_production'
  END,
  c.model_description,
  c.model_webpage
FROM public.cars c
WHERE c.is_model_rep = TRUE AND c.make_model_slug IS NOT NULL
ON CONFLICT (slug) DO NOTHING;

-- 3. Link trims to their model (make_model_slug kept for API compatibility)
ALTER TABLE public.cars ADD COLUMN IF NOT EXISTS model_id INTEGER REFERENCES public.models(id);
UPDATE public.cars c
SET model_id = m.id
FROM public.models m
WHERE c.make_model_slug = m.slug AND c.model_id IS NULL;

-- 4. Provenance columns: where data came from and when it was last confirmed
ALTER TABLE public.cars  ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;
ALTER TABLE public.cars  ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE public.makes ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;
ALTER TABLE public.makes ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE public.makes ADD COLUMN IF NOT EXISTS update_cadence TEXT NOT NULL DEFAULT 'model_year'
  CHECK (update_cadence IN ('continuous','model_year','irregular'));

-- 5. Cadence drives crawl frequency: continuous-update brands get daily checks
UPDATE public.makes SET update_cadence = 'continuous'
WHERE name IN ('Tesla','Rivian','Lucid','Polestar');
UPDATE public.makes SET update_cadence = 'irregular'
WHERE name IN ('BYD','NIO','XPeng','Geely');

CREATE INDEX IF NOT EXISTS idx_models_make_id ON public.models(make_id);
CREATE INDEX IF NOT EXISTS idx_cars_model_id ON public.cars(model_id);
