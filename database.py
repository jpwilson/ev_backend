import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from dotenv import load_dotenv

load_dotenv()

# URL_DATABASE = "sqlite:///./eevee.db" - old sqlite db
URL_DATABASE = os.getenv("URL_DATABASE", "postgresql://user:password@localhost/dbname")


engine = create_engine(URL_DATABASE)  # , connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

metadata = Base.metadata
