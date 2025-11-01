"""Database setup and session helpers.
Adds safe column creation for validation status fields.
"""
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session

# Read from env. Fallback to local SQLite only if env var is missing.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")

# Railway may provide 'postgresql://'. SQLAlchemy needs the psycopg driver.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# SSL for Railway proxy hosts — kept as-is.
connect_args = {"sslmode": "require"} if ".proxy.rlwy.net" in DATABASE_URL else {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

def init_db() -> None:
    """Create tables and ensure new columns exist (idempotent)."""
    # Ensure models are imported so tables are registered
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(bind=engine)

    # Idempotent column adds for existing product table.
    # Keeps current DB approach; no migrations framework.
    with engine.connect() as conn:
        conn.exec_driver_sql("ALTER TABLE product ADD COLUMN IF NOT EXISTS ean_status TEXT")
        conn.exec_driver_sql("ALTER TABLE product ADD COLUMN IF NOT EXISTS price_status TEXT")
        conn.exec_driver_sql("ALTER TABLE product ADD COLUMN IF NOT EXISTS image_status TEXT")
        conn.exec_driver_sql("ALTER TABLE product ADD COLUMN IF NOT EXISTS validation_result TEXT")

def get_session() -> Generator[Session, None, None]:
    """Yield a SQLModel Session bound to the engine."""
    with Session(engine) as session:
        yield session
