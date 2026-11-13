from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def canonical_source_url(value):
    parsed = urlsplit(str(value))
    if parsed.username or parsed.password:
        raise ValueError("A URL da vaga não pode conter credenciais.")
    ignored = {"jobboardsource", "trackingid", "refid", "trk", "utm_source", "utm_medium",
               "utm_campaign", "utm_term", "utm_content"}
    pairs = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=100)
             if key.casefold() not in ignored]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), parsed.fragment))


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(min_length=2, max_length=200)
    location: str = Field(default="Remoto", max_length=200)
    description: str = Field(min_length=20, max_length=50000)
    source_url: HttpUrl
    skills: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("source_url")
    @classmethod
    def normalize_source_url(cls, value):
        return HttpUrl(canonical_source_url(value))


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
