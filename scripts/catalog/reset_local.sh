#!/usr/bin/env bash
# Rebuild the LOCAL catalog database from scratch:
#   snapshot (production as of 2026-11-10) -> migrations 002/003 -> alembic head -> seed files.
# Usage: scripts/catalog/reset_local.sh [--skip-002-003]
# Env: PY (python with backend deps; default ../_catalog_work/venv/bin/python),
#      CATALOG_DB_URL (default postgresql://postgres@localhost:54329/evlineup; must be local).
set -euo pipefail
cd "$(dirname "$0")/../.."
PY="${PY:-../_catalog_work/venv/bin/python}"
URL="${CATALOG_DB_URL:-postgresql://postgres@localhost:54329/evlineup}"
# database.py / alembic env.py call load_dotenv(); pin every variable it reads so .env never wins.
export DATABASE_URL="$URL" SUPABASE_DATABASE_URL="$URL" USE_LOCAL_DB=false CATALOG_DB_URL="$URL"

"$PY" scripts/catalog/load_snapshot.py --db-url "$URL" --reset "$@"
"$PY" -m alembic upgrade head
"$PY" scripts/catalog/load_seed.py --db-url "$URL" --apply
