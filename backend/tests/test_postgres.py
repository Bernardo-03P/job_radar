"""Integração opcional: exclusivamente em banco descartável job_radar_audit."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.session import Base, migrate_database
from app.services.generation_lock import DatabaseGenerationLease


@pytest.fixture
def postgres():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL ausente; teste exige banco descartável.")
    parsed = make_url(url)
    if parsed.database != "job_radar_audit" or parsed.host not in {"127.0.0.1", "localhost"}:
        pytest.fail("Testes PostgreSQL permitidos somente no banco local job_radar_audit.")
    schema = "audit_" + uuid4().hex
    bootstrap = create_engine(url)
    with bootstrap.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    database = create_engine(url, connect_args={"options": f"-c search_path={schema},public"})
    try:
        yield database
    finally:
        database.dispose()
        assert schema.startswith("audit_") and len(schema) == 38 and schema[6:].isalnum()
        with bootstrap.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        bootstrap.dispose()


def test_postgres_concurrent_migrations_are_serialized(postgres):
    def migrate():
        with postgres.begin() as connection:
            migrate_database(connection)
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda _: migrate(), range(3)))
    assert {"jobs", "resume_versions", "alembic_version"} <= set(inspect(postgres).get_table_names())


def test_postgres_adopts_existing_rows(postgres):
    Base.metadata.create_all(postgres)
    with postgres.begin() as connection:
        connection.execute(text("INSERT INTO jobs (title,company,location,description,source_url,skills,created_at) "
                                "VALUES ('Teste','Sintética','Remoto','Python','https://example.com/a','[]',now())"))
        migrate_database(connection)
    with postgres.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM jobs")) == 1


def test_postgres_cross_process_generation_lock_releases_connection(postgres):
    with Session(postgres) as first, Session(postgres) as second:
        one = DatabaseGenerationLease(first, "synthetic-owner-source-job")
        two = DatabaseGenerationLease(second, "synthetic-owner-source-job")
        one.acquire()
        try:
            with pytest.raises(HTTPException) as error:
                two.acquire()
            assert error.value.status_code == 409
        finally:
            one.release()
        two.acquire()
        two.release()
        assert two.connection is None
