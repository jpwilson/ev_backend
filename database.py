import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from dotenv import load_dotenv

load_dotenv()

# DATABASE_URL = "sqlite:///./eevee.db" - old sqlite db
DATABASE_URL = os.getenv("DATABASE_URL").replace("postgres://", "postgresql://", 1)


engine = create_engine(DATABASE_URL)  # , connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

metadata = Base.metadata
