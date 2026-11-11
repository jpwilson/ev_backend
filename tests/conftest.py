"""Catalog test harness: builds throwaway local Postgres databases from the
production snapshot, migrates them and loads seeds.

Needs the local Postgres from _catalog_work (port 54329). Override with
CATALOG_TEST_PG=postgresql://user@host:port (server URL without a database).
Two databases are (re)created per session:
  evlineup_test_fixture  snapshot + tests/fixtures/catalog/*.json + catalog/data/_example.json
  evlineup_test_real     snapshot + catalog/data/*.json (whatever researchers have written)
"""
import json
import os
import sys

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER = os.getenv("CATALOG_TEST_PG", "postgresql://postgres@localhost:54329")
FIXTURE_DB = SERVER + "/evlineup_test_fixture"
REAL_DB = SERVER + "/evlineup_test_real"

# Pin the app to a local database before anything imports database.py (it calls
# load_dotenv(), which must never pull a remote URL into a test run).
os.environ["SUPABASE_DATABASE_URL"] = FIXTURE_DB
os.environ["DATABASE_URL"] = FIXTURE_DB
os.environ["USE_LOCAL_DB"] = "false"
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "scripts", "catalog"))

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

FIXTURE_FILES = [
    os.path.join(BACKEND, "tests", "fixtures", "catalog", "fisker.json"),
    os.path.join(BACKEND, "tests", "fixtures", "catalog", "tesla.json"),
    os.path.join(BACKEND, "catalog", "data", "_example.json"),
]
LEGACY_MODEL_SLUGS = ["tesla-model-3", "fisker-ocean", "cadillac-lyriq", "hyundai-ioniq-5", "porsche-taycan"]
CATALOG_TABLES = ["makes", "models", "generations", "cars", "variant_markets", "model_markets",
                  "model_relations", "images", "url_redirects"]


def _recreate(url):
    import psycopg2
    server, name = url.rsplit("/", 1)
    conn = psycopg2.connect(server + "/postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS %s WITH (FORCE)" % name)
        cur.execute("CREATE DATABASE %s" % name)
    conn.close()


def _alembic(url, *args):
    from alembic import command
    from alembic.config import Config
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    cwd = os.getcwd()
    os.chdir(BACKEND)
    try:
        getattr(command, args[0])(cfg, *args[1:])
    finally:
        os.chdir(cwd)
        os.environ["DATABASE_URL"] = old


def load_seeds(engine, files):
    import load_seed
    with engine.connect() as conn:
        with conn.begin():
            return load_seed.run(conn, files)


def row_counts(engine):
    with engine.connect() as conn:
        return {t: conn.execute(text("SELECT count(*) FROM %s" % t)).scalar() for t in CATALOG_TABLES}


class Env:
    """One test database plus a TestClient bound to it."""

    def __init__(self, url):
        from fastapi.testclient import TestClient
        import main
        from dependencies import get_db
        self.url = url
        self.engine = create_engine(url, poolclass=NullPool)
        Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

        def _get_db():
            db = Session()
            try:
                yield db
            finally:
                db.close()
        self.app = main.app
        self._override = (get_db, _get_db)
        self.client = TestClient(main.app)

    def get(self, path):
        self.app.dependency_overrides[self._override[0]] = self._override[1]
        return self.client.get(path)


def legacy_snapshot(env):
    """Raw bodies of the legacy endpoints the catalog must not disturb."""
    out = {"/cars/cards": env.get("/cars/cards"), "/makes": env.get("/makes")}
    for s in LEGACY_MODEL_SLUGS:
        out["/cars/model-details/" + s] = env.get("/cars/model-details/" + s)
    return {k: (r.status_code, r.content) for k, r in out.items()}


def canonical(path, body, drop_car_ids=(), drop_make_ids=()):
    """Order-insensitive form (legacy queries have no ORDER BY, so Postgres may return
    rows in any order after an UPDATE) with rows the catalog loader added removed."""
    data = json.loads(body)
    if path == "/cars/cards":
        data = sorted((c for c in data if c["id"] not in drop_car_ids), key=lambda c: c["id"])
    elif path == "/makes":
        data = sorted((m for m in data if m["id"] not in drop_make_ids), key=lambda m: m["id"])
        for m in data:
            m["car_id_list"] = sorted(i for i in m["car_id_list"] if i not in drop_car_ids)
    elif isinstance(data, dict) and "submodels" in data:
        data["submodels"] = sorted((s for s in data["submodels"] if s["id"] not in drop_car_ids),
                                   key=lambda s: s["id"])
        gens = []
        for g in data["previous_generations"]:
            g["submodels"] = sorted((s for s in g["submodels"] if s["id"] not in drop_car_ids),
                                    key=lambda s: s["id"])
            if g["submodels"]:
                gens.append(g)
        data["previous_generations"] = sorted(gens, key=lambda g: g["generation"] or "")
    return json.dumps(data, ensure_ascii=False)


def fill_empty_logos(path, before, after):
    """The loader may fill an empty makes.lrg_logo_img_url from a seed logo (never replace
    one). For /makes, give `before` the logo that was filled so the rest still compares."""
    if path != "/makes":
        return before
    filled = {m["id"]: m.get("lrg_logo_img_url") for m in json.loads(after)}
    data = json.loads(before)
    for m in data:
        if not (m.get("lrg_logo_img_url") or "").strip() and filled.get(m["id"]):
            m["lrg_logo_img_url"] = filled[m["id"]]
    return json.dumps(data, ensure_ascii=False)


def added_rows(engine):
    with engine.connect() as conn:
        cars = {r[0] for r in conn.execute(text("SELECT id FROM cars WHERE catalog_origin = 'seed'"))}
        makes = {r[0] for r in conn.execute(text("SELECT id FROM makes WHERE catalog_origin = 'seed'"))}
    return cars, makes


def _build(url, files):
    import load_snapshot
    _recreate(url)
    load_snapshot.main(["--db-url", url, "--reset"])
    env = Env(url)
    state = {"env": env, "before": legacy_snapshot(env), "meta_before": env.get("/catalog/meta")}
    _alembic(url, "upgrade", "head")
    state["after_migration"] = legacy_snapshot(env)
    state["report"] = load_seeds(env.engine, files)
    state["after_load"] = legacy_snapshot(env)
    state["files"] = files
    return state


@pytest.fixture(scope="session")
def fixture_db():
    return _build(FIXTURE_DB, FIXTURE_FILES)


@pytest.fixture(scope="session")
def real_db():
    import load_seed
    return _build(REAL_DB, load_seed.expand([os.path.join(BACKEND, "catalog", "data")]))
