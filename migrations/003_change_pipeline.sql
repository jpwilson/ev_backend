-- ============================================
-- 003: Change-proposal pipeline (crawlers propose, humans approve)
-- Run in Supabase SQL Editor after 002.
-- Iron rule: crawlers never write to cars/makes/models directly —
-- they write change_proposals; approval applies them.
-- ============================================

-- 1. Crawl runs: one row per fetcher execution, for stats + debugging
CREATE TABLE IF NOT EXISTS public.crawl_runs (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,                     -- e.g. 'epa_range_check', 'vpic_roster'
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running','completed','failed')),
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

-- 2. Change proposals: the Data Inbox
CREATE TABLE IF NOT EXISTS public.change_proposals (
  id BIGSERIAL PRIMARY KEY,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('car','make','model')),
  entity_id INTEGER NOT NULL,
  field TEXT NOT NULL,
  old_value JSONB,                         -- value at proposal time (JSON for type fidelity)
  new_value JSONB,
  source_name TEXT,                        -- e.g. 'EPA fueleconomy.gov'
  source_url TEXT,
  confidence REAL,                         -- 0..1, fetcher's own certainty
  rationale TEXT,                          -- human-readable why
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected','auto_applied')),
  crawl_run_id BIGINT REFERENCES public.crawl_runs(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  applied_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_change_proposals_status ON public.change_proposals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_change_proposals_entity ON public.change_proposals(entity_type, entity_id);

-- 3. Price snapshots: queryable price history (feeds price-drop alerts +
--    the EV Radar digest; the JSON price_history blob on cars stays as-is)
CREATE TABLE IF NOT EXISTS public.price_snapshots (
  id BIGSERIAL PRIMARY KEY,
  car_id INTEGER NOT NULL REFERENCES public.cars(id) ON DELETE CASCADE,
  market TEXT NOT NULL DEFAULT 'US',
  currency TEXT NOT NULL DEFAULT 'USD',
  msrp NUMERIC(12,2),
  effective_price NUMERIC(12,2),
  source_url TEXT,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_price_snapshots_car ON public.price_snapshots(car_id, captured_at DESC);
