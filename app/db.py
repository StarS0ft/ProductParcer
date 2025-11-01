import os
import logging
from typing import Generator

from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session

log = logging.getLogger("app.db")

# Read from env. Fallback to local SQLite only if env var is missing.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")

# Railway often provides 'postgresql://'. SQLAlchemy needs the psycopg driver.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# SSL for Railway proxy hosts (safe to leave on)
connect_args = {"sslmode": "require"} if ".proxy.rlwy.net" in DATABASE_URL else {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args
)

def init_db() -> None:
    # Ensure models are imported so tables are registered
    from . import models  # noqa
    SQLModel.metadata.create_all(bind=engine)

    # Add only the title-related columns (idempotent)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE product ADD COLUMN IF NOT EXISTS name_status TEXT")
            conn.exec_driver_sql("ALTER TABLE product ADD COLUMN IF NOT EXISTS name_suggested TEXT")
    except Exception as e:
        log.warning("Skipping column ensure (name_*): %s", e)

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
