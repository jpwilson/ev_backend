#!/usr/bin/env python3
"""Build a local copy of the production legacy database from the JSON snapshot.

Creates the legacy tables (cars, makes, people and the make/person association
tables) from the existing ORM, adjusts them to match the production schema
(taken from the Feb 2026 dump: no unique index on cars.full_slug, jsonb where
production has jsonb, CEO tenure dates), loads _catalog_work/snapshot/*.json with
the original ids, stamps alembic_version at a3f8b2c1d4e5 (production's head), and
by default applies migrations/002 + 003 as production most likely has them.

Local databases only. Usage:
  python scripts/catalog/load_snapshot.py --reset            # wipe schema public, rebuild
  python scripts/catalog/load_snapshot.py --reset --skip-002-003
  python scripts/catalog/load_snapshot.py --db-url postgresql://postgres@localhost:54329/evlineup_test --reset
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from _common import BACKEND_DIR, WORK_DIR, guard_url, pin_env, resolve_db_url  # noqa: E402

LEGACY_TABLES = [
    "makes", "people", "cars",
    "make_person_association", "make_founders_association", "make_ceo_association",
]

# Production differs from what create_all() would emit; make local match production.
PARITY_SQL = [
    # create_all makes these indexes from index=True / unique=True; production has none.
    "DROP INDEX IF EXISTS ix_cars_full_slug",
    "DROP INDEX IF EXISTS ix_cars_availability_desc",
    # Alembic a3f8b2c1d4e5 / 1e787786a3a0 created these as jsonb.
    "ALTER TABLE cars ALTER COLUMN images TYPE jsonb USING images::jsonb",
    "ALTER TABLE people ALTER COLUMN current_roles TYPE jsonb USING current_roles::jsonb",
    "ALTER TABLE people ALTER COLUMN previous_roles TYPE jsonb USING previous_roles::jsonb",
    # Alembic 7a920b3f1e8a.
    "ALTER TABLE make_ceo_association ADD COLUMN IF NOT EXISTS start_date date",
    "ALTER TABLE make_ceo_association ADD COLUMN IF NOT EXISTS end_date date",
    "CREATE TABLE IF NOT EXISTS alembic_version ("
    " version_num varchar(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))",
]

PROD_ALEMBIC_HEAD = "a3f8b2c1d4e5"


def _parse_ts(v):
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return v
    return v


def _rows(path, table, drop=()):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cols = set(table.c.keys())
    out = []
    for r in data:
        row = {k: v for k, v in r.items() if k in cols and k not in drop}
        if "updated_at" in row:
            row["updated_at"] = _parse_ts(row["updated_at"])
        out.append(row)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-url", help="default: CATALOG_DB_URL or the local dev database")
    ap.add_argument("--snapshot-dir", default=os.path.join(WORK_DIR, "snapshot"))
    ap.add_argument("--reset", action="store_true", help="DROP SCHEMA public CASCADE first")
    ap.add_argument("--skip-002-003", action="store_true",
                    help="do not apply migrations/002 + 003 (simulates a production without them)")
    args = ap.parse_args(argv)

    url = resolve_db_url(args.db_url)
    guard_url(url)  # never remote
    pin_env(url)

    from sqlalchemy import create_engine, text
    import database  # noqa: F401  (Base)
    import models.orm_models  # noqa: F401  (registers legacy tables on Base.metadata)
    from database import Base

    engine = create_engine(url)
    md = Base.metadata
    with engine.begin() as conn:
        if args.reset:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        existing = conn.execute(text("SELECT to_regclass('public.cars')")).scalar()
        if existing and not args.reset:
            sys.exit("cars already exists; pass --reset to rebuild")
        md.create_all(conn, tables=[md.tables[t] for t in LEGACY_TABLES])
        for stmt in PARITY_SQL:
            conn.execute(text(stmt))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": PROD_ALEMBIC_HEAD})

        counts = {}
        for name, fname, drop in (
            ("people", "people.json", ()),
            ("makes", "makes.json", ("car_id_list",)),
            ("cars", "cars_all.json", ("average_rating",)),
        ):
            rows = _rows(os.path.join(args.snapshot_dir, fname), md.tables[name], drop)
            if rows:
                conn.execute(md.tables[name].insert(), rows)
            conn.execute(text(
                "SELECT setval(pg_get_serial_sequence('%s', 'id'), "
                "(SELECT coalesce(max(id), 1) FROM %s))" % (name, name)))
            counts[name] = len(rows)

        if not args.skip_002_003:
            for f in ("002_models_and_provenance.sql", "003_change_pipeline.sql"):
                with open(os.path.join(BACKEND_DIR, "migrations", f), encoding="utf-8") as fh:
                    # raw cursor, no parameters: the SQL contains literal '%' (ILIKE)
                    conn.connection.cursor().execute(fh.read())
            counts["models (002 backfill)"] = conn.execute(text("SELECT count(*) FROM models")).scalar()

    print("Loaded into %s: %s; alembic_version=%s; 002/003 %s" % (
        url.rsplit("/", 1)[-1], ", ".join("%s=%d" % kv for kv in counts.items()),
        PROD_ALEMBIC_HEAD, "skipped" if args.skip_002_003 else "applied"))


if __name__ == "__main__":
    main()
