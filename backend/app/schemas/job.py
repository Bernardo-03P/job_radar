from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(min_length=2, max_length=200)
    location: str = Field(default="Remoto", max_length=200)
    description: str = Field(min_length=20, max_length=50000)
    source_url: HttpUrl
    skills: list[str] = Field(default_factory=list, max_length=50)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    company: str
    location: str
    description: str
    source_url: str
    skills: list[str]
    created_at: datetime
