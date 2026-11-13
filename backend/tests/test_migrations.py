import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.db.session import Base, migrate_database
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.schemas.resume import TailorResponseData
from tests.test_api_routes import JOB


def engine():
    return create_engine("sqlite://")


def test_migration_creates_versioned_schema_and_is_idempotent():
    database = engine()
    with database.begin() as connection:
        migrate_database(connection)
    with database.begin() as connection:
        migrate_database(connection)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_initial"
    assert {"jobs", "resume_versions", "alembic_version"} <= set(inspect(database).get_table_names())
    database.dispose()


def test_migration_adopts_existing_schema_without_changing_resume_data():
    database = engine()
    Base.metadata.create_all(database)
    with Session(database) as session:
        job = Job(**JOB)
        session.add(job)
        session.flush()
        data = TailorResponseData(match_score=50, summary_of_changes=[], missing_critical_skills=[],
                                  adapted_resume_markdown="# Candidata sintética\nPython").model_dump()
        version = ResumeVersion(owner_hash="a" * 64, source_fingerprint="b" * 64,
                                context_hash="c" * 64, job_id=job.id, job_title=job.title,
                                company=job.company, job_description=job.description, data=data)
        session.add(version)
        session.commit()
        version_id = version.id
    with database.begin() as connection:
        migrate_database(connection)
    with Session(database) as session:
        assert session.get(ResumeVersion, version_id).data == data
        assert len(session.scalars(select(Job)).all()) == 1
    database.dispose()


def test_migration_rejects_incompatible_schema_without_deleting_rows():
    database = engine()
    with database.begin() as connection:
        connection.execute(text("CREATE TABLE jobs (id INTEGER PRIMARY KEY, marker TEXT)"))
        connection.execute(text("INSERT INTO jobs VALUES (1, 'preserve-me')"))
    with pytest.raises(RuntimeError, match="incompatível"):
        with database.begin() as connection:
            migrate_database(connection)
    with database.connect() as connection:
        assert connection.scalar(text("SELECT marker FROM jobs WHERE id=1")) == "preserve-me"
    database.dispose()
