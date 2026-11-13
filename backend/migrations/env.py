from alembic import context

from app.db.session import Base
from app.models.job import Job  # noqa: F401
from app.models.resume_version import ResumeVersion  # noqa: F401

config = context.config


def run():
    connection = config.attributes.get("connection")
    if connection is None:
        from app.db.session import engine
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            run()
        return
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run()
