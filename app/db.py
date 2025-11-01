import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"sslmode": "require"} if ".proxy.rlwy.net" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)

EXTRA_COLUMNS = [
    ("ean_status", "TEXT"),
    ("price_status", "TEXT"),
    ("image_status", "TEXT"),
    ("validation_result", "TEXT"),
]


def auto_add_columns():
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
                )
            )
        }
        for col, coltype in EXTRA_COLUMNS:
            if col not in cols:
                conn.execute(text(f"ALTER TABLE products ADD COLUMN {col} {coltype}"))
        conn.commit()


def init_db():
    from . import models  # register tables  # noqa: F401

    SQLModel.metadata.create_all(bind=engine)
    try:
        auto_add_columns()  # <—— THIS IS THE MAGIC
    except Exception:
        pass


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
