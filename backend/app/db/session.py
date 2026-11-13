from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, pool_timeout=10, pool_recycle=1800,
                       connect_args={"connect_timeout": 10,
                                     "options": "-c statement_timeout=15000 -c idle_in_transaction_session_timeout=30000"})
SessionLocal = sessionmaker(bind=engine)


def migrate_database(connection):
    from alembic import command
    from alembic.config import Config
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(741309116)"))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


def initialize_database():
    with engine.begin() as connection:
        migrate_database(connection)


def get_db():
    with SessionLocal() as session:
        yield session
