from pathlib import Path

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

DATABASE_URL = settings.database_url
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE and ":memory:" not in DATABASE_URL:
    # Make sure the folder for a file-based SQLite database exists.
    Path(DATABASE_URL.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=not IS_SQLITE,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Named constraints: required for SQLite batch migrations and predictable downgrades.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
