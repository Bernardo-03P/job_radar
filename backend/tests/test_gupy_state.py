import json

import httpx
import pytest
from agent.public_jobs import fetch_gupy


def document(**changes):
    job = {"id": 123, "company": {"subdomain": "example"}, "careerPage": {"name": "Empresa"},
           "name": "Estágio em Dados", "description": "Desenvolver projetos em Python.",
           "responsibilities": "Consultas SQL.", "prerequisites": "Cursando ADS.",
           "relevantExperiences": "Benefícios.", "status": "published", "publicationType": "external",
           "workplaceType": "remote", "addressCountry": "Brasil", "expiresAt": "2099-01-01"} | changes
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(
        {"props": {"pageProps": {"job": job}}}) + "</script>"


def fetch(**changes):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=document(**changes)))) as client:
        return fetch_gupy(client, "https://example.gupy.io/jobs/123")


def test_public_state_includes_requirements_and_explicit_remote_country():
    raw, company = fetch()[0]
    assert company == "Empresa"
    assert raw["location"]["name"] == "Remoto, Brasil"
    assert "Consultas SQL" in raw["content"] and "Cursando ADS" in raw["content"]


@pytest.mark.parametrize("changes", [{"status": "closed"}, {"publicationType": "internal"},
                                   {"expiresAt": "2020-01-01"}, {"registerEndDate": "2020-01-01"}])
def test_closed_expired_or_internal_state_is_not_imported(changes):
    assert fetch(**changes) == []


@pytest.mark.parametrize("changes", [{"id": 999}, {"company": {"subdomain": "other"}},
                                   {"prerequisites": None}, {"careerPage": {}}])
def test_wrong_identity_or_missing_evidence_is_rejected(changes):
    with pytest.raises(ValueError):
        fetch(**changes)
