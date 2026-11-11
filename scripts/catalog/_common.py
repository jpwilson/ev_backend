"""Shared helpers for the catalog scripts (local stack, database URL, safety guard).

The backend's database.py and auth.py call load_dotenv(), which would pull the
production URL from ev_backend/.env if SUPABASE_DATABASE_URL / DATABASE_URL are
not already set. Every script here therefore pins both variables to the URL it
was given *before* importing any backend module, and refuses non-local hosts
unless explicitly allowed.
"""
import os
import sys
from urllib.parse import urlparse

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORK_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "..", "_catalog_work"))
DEFAULT_LOCAL_URL = "postgresql://postgres@localhost:54329/evlineup"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def resolve_db_url(cli_value=None):
    """--db-url, else CATALOG_DB_URL, else the local dev database."""
    url = cli_value or os.getenv("CATALOG_DB_URL") or DEFAULT_LOCAL_URL
    return url.replace("postgres://", "postgresql://", 1)


def is_local(url):
    return (urlparse(url).hostname or "") in LOCAL_HOSTS


def guard_url(url, allow_remote=False):
    if not is_local(url) and not allow_remote:
        sys.exit(
            "Refusing to touch a non-local database (%s). "
            "Pass --allow-remote only when the owner has said go." % (urlparse(url).hostname,)
        )


def pin_env(url):
    """Make backend modules (database.py) use this URL instead of anything in .env."""
    os.environ["SUPABASE_DATABASE_URL"] = url
    os.environ["DATABASE_URL"] = url
    # set (not pop): load_dotenv() would otherwise fill it from .env and switch to SQLite
    os.environ["USE_LOCAL_DB"] = "false"
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)
