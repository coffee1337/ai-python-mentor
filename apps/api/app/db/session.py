import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    if os.getenv("APP_ENV", "development").casefold() == "production":
        raise RuntimeError("DATABASE_URL is required in production")
    DATABASE_URL = "postgresql+psycopg://mentor:change_this_local_password@localhost:5432/mentor"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
