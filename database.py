import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from dotenv import load_dotenv

load_dotenv()

# Use SQLite for local dev if USE_LOCAL_DB=true, otherwise use PostgreSQL
_use_local = os.getenv("USE_LOCAL_DB", "").lower() == "true"
_db_url = os.getenv("DATABASE_URL")

if _use_local:
    # Local development - SQLite
    DATABASE_URL = "sqlite:///./ev_local.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
elif _db_url:
    DATABASE_URL = _db_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    # Fallback to SQLite if no DATABASE_URL
    DATABASE_URL = "sqlite:///./ev_local.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

metadata = Base.metadata
