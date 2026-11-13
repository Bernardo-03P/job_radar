from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TailorResponseData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match_score: int = Field(ge=0, le=100)
    summary_of_changes: list[str]
    missing_critical_skills: list[str]
    adapted_resume_markdown: str


class SavedResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    job_id: int | None
    job_title: str
    company: str
    job_description: str
    source_fingerprint: str
    created_at: datetime
    data: TailorResponseData


class TailorResponse(BaseModel):
    status: Literal["success"] = "success"
    data: TailorResponseData
    version: SavedResumeRead | None = None
    cached: bool = False


class SavedSourceTailorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    job_id: int = Field(ge=1)
