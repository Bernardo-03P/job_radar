import base64
import json

import httpx
import pytest
from agent.job_profile import load_profile, profile_match

from app.models.job import Job
from app.schemas.job import canonical_source_url
from main import app


def alias(payload, domain="example.gupy.io"):
    token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"https://{domain}/job/{token}"


def test_gupy_share_link_and_original_have_same_identity():
    assert canonical_source_url(alias({"jobId": 123, "source": "gupy_portal"})) == (
        "https://example.gupy.io/jobs/123")


@pytest.mark.parametrize("payload", [{"jobId": True}, {"jobId": -1}, {"jobId": "123"}, [], {}])
def test_invalid_share_payload_is_not_merged(payload):
    url = alias(payload)
    assert canonical_source_url(url) == url


def test_share_decoding_is_limited_to_original_gupy_domains():
    url = alias({"jobId": 123}, domain="example.gupy.io.evil.test")
    assert canonical_source_url(url) == url
    assert canonical_source_url("https://example.gupy.io/job/not-json") == "https://example.gupy.io/job/not-json"


async def test_legacy_duplicate_is_hidden_from_recommendations_but_history_preserved(database):
    with database() as db:
        for url in ["https://example.gupy.io/jobs/123", alias({"jobId": 123})]:
            db.add(Job(title="Estágio em Dados", company="Empresa teste", location="Remoto, Brasil",
                       description="Projetos de dados em Python e SQL.", source_url=url, skills=["Python"]))
        db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        recommended = (await client.get("/api/v1/jobs?matching_profile=true")).json()
        assert len(recommended) == 1
        assert recommended[0]["source_url"] == "https://example.gupy.io/jobs/123"
        assert len((await client.get("/api/v1/jobs")).json()) == 2


def test_inferred_headquarters_does_not_override_unconfirmed_vacancy_address():
    job = {"title": "Estágio em Dados", "location": "Florianópolis, Trindade, presencial",
           "description": "Python e SQL. Anúncio não especifica bairro; confirmar endereço exato."}
    assert profile_match(job, load_profile()) == (False, "florianopolis_bairro_a_confirmar")
