from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(default="postgresql+psycopg://postgres:postgrespassword@localhost:5432/job_radar_db", repr=False)
    groq_api_key: str = Field(default="", repr=False)
    openai_api_key: str = Field(default="", repr=False)
    groq_model: str = "openai/gpt-oss-120b"
    openai_model: str = "gpt-4o-mini"
    ingest_api_key: str = Field(default="", repr=False)
    resume_api_key: str = Field(default="", repr=False)
    upload_timeout_seconds: float = Field(default=15, gt=0, le=120)
    max_concurrent_uploads: int = Field(default=4, ge=1, le=32)
    pdf_timeout_seconds: float = Field(default=15, gt=0, le=60)
    llm_max_output_tokens: int = Field(default=4096, ge=256, le=8192)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()
