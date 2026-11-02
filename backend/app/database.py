import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DB_NAME

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing. Create Homework4/.env from .env.example.")

# HW8: inside Docker "localhost" is the container itself, so docker-compose.yml sets
# DATABASE_HOST_OVERRIDE=host.docker.internal to reach the MySQL server on the Mac.
if os.getenv("DATABASE_HOST_OVERRIDE"):
    DATABASE_URL = make_url(DATABASE_URL).set(host=os.environ["DATABASE_HOST_OVERRIDE"])

if make_url(DATABASE_URL).database != DB_NAME:
    raise RuntimeError(f"DATABASE_URL must point at the {DB_NAME} database.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Database connection/session factory.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
