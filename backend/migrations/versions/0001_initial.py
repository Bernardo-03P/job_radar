"""Baseline idempotente: adota o esquema anterior sem apagar dados."""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def ensure_columns(name, expected):
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(name):
        return False
    actual = {column["name"] for column in inspector.get_columns(name)}
    if not set(expected).issubset(actual):
        raise RuntimeError("Esquema existente incompatível; migração interrompida sem apagar dados.")
    return True


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if not ensure_columns("jobs", ("id", "title", "company", "location", "description", "source_url", "skills", "embedding", "created_at")):
        op.create_table("jobs", sa.Column("id", sa.Integer(), primary_key=True),
                        sa.Column("title", sa.String(200), nullable=False),
                        sa.Column("company", sa.String(200), nullable=False),
                        sa.Column("location", sa.String(200), nullable=False),
                        sa.Column("description", sa.Text(), nullable=False),
                        sa.Column("source_url", sa.String(2000), nullable=False, unique=True),
                        sa.Column("skills", sa.JSON(), nullable=False),
                        sa.Column("embedding", Vector(384), nullable=True),
                        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    if not ensure_columns("resume_versions", ("id", "owner_hash", "source_fingerprint", "context_hash", "job_id", "job_title", "company", "job_description", "data", "created_at")):
        op.create_table("resume_versions", sa.Column("id", sa.String(36), primary_key=True),
                        sa.Column("owner_hash", sa.String(64), nullable=False),
                        sa.Column("source_fingerprint", sa.String(64), nullable=False),
                        sa.Column("context_hash", sa.String(64), nullable=False),
                        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=True),
                        sa.Column("job_title", sa.String(200), nullable=False),
                        sa.Column("company", sa.String(200), nullable=False),
                        sa.Column("job_description", sa.Text(), nullable=False),
                        sa.Column("data", sa.JSON(), nullable=False),
                        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                        sa.UniqueConstraint("owner_hash", "source_fingerprint", "context_hash",
                                            name="uq_resume_owner_source_context"))
        op.create_index("ix_resume_versions_owner_hash", "resume_versions", ["owner_hash"])
        op.create_index("ix_resume_versions_source_fingerprint", "resume_versions", ["source_fingerprint"])


def downgrade():
    raise RuntimeError("Downgrade destrutivo indisponível; restaure um backup para reverter o esquema.")
