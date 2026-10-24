
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./pest_guard.db",
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1,
    )

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)

    # Safely migrate existing databases.
    # create_all() does not add columns to existing tables.
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = inspector.get_table_names()

        if "detections" not in tables:
            return

        columns = {
            column["name"]
            for column in inspector.get_columns("detections")
        }

        if "top_predictions" not in columns:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "ALTER TABLE detections "
                        "ADD COLUMN IF NOT EXISTS top_predictions TEXT"
                    )
                )
            else:
                connection.execute(
                    text(
                        "ALTER TABLE detections "
                        "ADD COLUMN top_predictions TEXT"
                    )
                )
