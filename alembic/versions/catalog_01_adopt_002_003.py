"""Adopt hand-run SQL migrations 002 + 003 into Alembic, idempotently.

Whether 002/003 ever ran in production is unknown, so every statement is
IF NOT EXISTS. 002's data backfill (INSERT INTO models ... / UPDATE cars SET
model_id) is deliberately skipped: its status mapping is wrong and the catalog
seed loader fills models instead. Row-level security is enabled on the 002/003
tables (no policies: the backend connects as the table owner, which bypasses
RLS; Supabase's anon Data API gets nothing).

Revision ID: catalog_01_adopt_002_003
Revises: a3f8b2c1d4e5
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "catalog_01_adopt_002_003"
down_revision: Union[str, None] = "a3f8b2c1d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATEMENTS = [
    # ---- 002: models + provenance columns (DDL only)
    """CREATE TABLE IF NOT EXISTS models (
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
)""",
    "ALTER TABLE cars ADD COLUMN IF NOT EXISTS model_id INTEGER REFERENCES models(id)",
    "ALTER TABLE cars ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ",
    "ALTER TABLE cars ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE makes ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ",
    "ALTER TABLE makes ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb",
    """ALTER TABLE makes ADD COLUMN IF NOT EXISTS update_cadence TEXT NOT NULL DEFAULT 'model_year'
  CHECK (update_cadence IN ('continuous','model_year','irregular'))""",
    "CREATE INDEX IF NOT EXISTS idx_models_make_id ON models(make_id)",
    "CREATE INDEX IF NOT EXISTS idx_cars_model_id ON cars(model_id)",
    # ---- 003: change-proposal pipeline
    """CREATE TABLE IF NOT EXISTS crawl_runs (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running','completed','failed')),
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
)""",
    """CREATE TABLE IF NOT EXISTS change_proposals (
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
)""",
    "CREATE INDEX IF NOT EXISTS idx_change_proposals_status ON change_proposals(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_change_proposals_entity ON change_proposals(entity_type, entity_id)",
    """CREATE TABLE IF NOT EXISTS price_snapshots (
  id BIGSERIAL PRIMARY KEY,
  car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  market TEXT NOT NULL DEFAULT 'US',
  currency TEXT NOT NULL DEFAULT 'USD',
  msrp NUMERIC(12,2),
  effective_price NUMERIC(12,2),
  source_url TEXT,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
    "CREATE INDEX IF NOT EXISTS idx_price_snapshots_car ON price_snapshots(car_id, captured_at DESC)",
    # ---- RLS (idempotent)
    "ALTER TABLE models ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE crawl_runs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE change_proposals ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE price_snapshots ENABLE ROW LEVEL SECURITY",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # No-op by design: these objects may predate this revision (002/003 were run
    # by hand in the Supabase SQL editor), so dropping them could destroy data
    # this revision never created.
    pass
