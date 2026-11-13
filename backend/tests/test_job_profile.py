import html
import json

import httpx
import pytest
from agent.job_profile import load_profile, prioritize, profile_match
from agent.public_jobs import fetch_gupy, fetch_gupy_board

from app.core.config import settings
from main import app


def job(title="Estágio em Ciência de Dados", location="Remoto, Brasil", description="Python e SQL"):
    return {"title": title, "location": location, "description": description}


@pytest.mark.parametrize("title", ["Estagiário em IA", "Estágio em Desenvolvimento de Sistemas",
                                  "Estagiária de Suporte N1", "Trainee em Dados"])
def test_areas_and_entry_levels(title):
    assert profile_match(job(title), load_profile())[0]


@pytest.mark.parametrize("title", ["Senior Data Scientist", "Analista de Dados Júnior",
                                  "Jovem Aprendiz de Tecnologia", "Estágio em Marketing"])
def test_other_levels_and_areas_are_not_selected(title):
    assert not profile_match(job(title, description="Comunicação e campanhas"), load_profile())[0]


@pytest.mark.parametrize("location", ["São José, SC", "Palhoça, SC", "Biguaçu, SC",
                                     "Florianópolis, Estreito", "Florianópolis, Coqueiros",
                                     "Grande Florianópolis", "Florianópolis, SC"])
def test_excluded_or_unconfirmed_physical_address(location):
    assert not profile_match(job(location=location), load_profile())[0]


def test_island_hybrid_and_remote_brazil_allowed():
    assert profile_match(job(location="Híbrido, Florianópolis, Saco Grande"), load_profile())[0]
    assert profile_match(job(location="Remoto, Brasil"), load_profile())[0]
    assert not profile_match(job(location="Remoto, México"), load_profile())[0]
    assert not profile_match(job(location="Híbrido, São José, Brasil"), load_profile())[0]
    assert not profile_match(job(description="Obrigatório residir em São Paulo"), load_profile())[0]
    assert not profile_match(job(location="Remoto, Brasil",
                                 description="Modelo de trabalho híbrido em São Paulo"), load_profile())[0]


def test_n2_is_secondary_and_required_experience_needs_review():
    profile = load_profile()
    assert profile_match(job("Estágio em Suporte N2", description="Treinamento oferecido"), profile)[0]
    assert not profile_match(job("Estágio em Suporte N2",
                                 description="Experiência mínima de 2 anos em suporte"), profile)[0]
    n2, n1 = job("Estágio em Suporte N2"), job("Estágio em Suporte N1")
    assert prioritize([n2, n1], 10, profile) == [n1, n2]


def test_ninety_percent_target_without_fabrication():
    internships = [job(f"Estágio em Dados {i}") for i in range(15)]
    trainees = [job(f"Trainee em Dados {i}") for i in range(15)]
    selected = prioritize(trainees + internships, 10, load_profile())
    assert len(selected) == 10
    assert sum("Estágio" in item["title"] for item in selected) == 9
    assert prioritize(internships[:2], 10, load_profile()) == internships[:2]


def page(expiry="2099-01-01"):
    data = {"@type": "JobPosting", "title": "Estágio em Suporte", "description": "Python e SQL",
            "validThrough": expiry, "hiringOrganization": {"name": "Empresa teste"},
            "jobLocation": {"address": {"addressCountry": "Brasil"},
                            "additionalProperty": {"value": "TELECOMMUTE"}}}
    return '<script type="application/ld+json">' + html.escape(json.dumps(data)) + '</script>'


@pytest.mark.parametrize("content,count", [(page(), 1), (page("2020-01-01"), 0),
                                         (page() + "Vaga encerrada", 0),
                                         (page() + "Applications closed", 0)])
def test_public_jobposting_checks_deadline_and_closed_notice(content, count):
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=content.encode("utf-8")))) as client:
        records = fetch_gupy(client, "https://example.gupy.io/jobs/123")
    assert len(records) == count
    if records:
        assert records[0][0]["location"]["name"] == "Remoto, Brasil"


def test_public_source_does_not_follow_external_links_or_fabricate_content():
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="Página sem dados"))) as client:
        with pytest.raises(ValueError):
            fetch_gupy(client, "https://evil.example/jobs/123")
        with pytest.raises(ValueError):
            fetch_gupy(client, "https://example.gupy.io/jobs/123")


def test_hidden_translation_does_not_mark_open_job_as_closed():
    content = page() + '<script type="application/json">{"translation":"Vaga encerrada"}</script>'
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=content.encode("utf-8")))) as client:
        assert len(fetch_gupy(client, "https://example.gupy.io/jobs/123")) == 1


async def test_api_profile_filters_before_pagination_without_deleting_history(mocker):
    mocker.patch.object(settings, "ingest_api_key", "test-ingest-key")
    dataset = [job("Senior Data Scientist"), job("Estágio em Dados"),
               job("Estágio em Suporte N1", location="São José, SC"), job("Trainee em Sistemas")]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for index, row in enumerate(dataset):
            response = await client.post("/api/v1/jobs", headers={"X-API-Key": "test-ingest-key"},
                                         json=row | {"company": "Empresa teste",
                                                     "description": "Python e SQL para construir sistemas.",
                                                     "source_url": f"https://example.com/jobs/{index}"})
            assert response.status_code == 201
        selected = (await client.get("/api/v1/jobs?matching_profile=true&limit=1")).json()
        assert [row["title"] for row in selected] == ["Estágio em Dados"]
        next_page = (await client.get("/api/v1/jobs?matching_profile=true&limit=1&offset=1")).json()
        assert [row["title"] for row in next_page] == ["Trainee em Sistemas"]
        assert len((await client.get("/api/v1/jobs")).json()) == 4


def test_public_board_discovers_entry_jobs_and_ignores_senior_and_duplicate_links():
    state = {"props": {"pageProps": {"jobs": [
        {"id": 1, "title": "Estágio em Suporte N1"},
        {"id": 1, "title": "Estágio em Suporte N1"},
        {"id": 2, "title": "Senior Data Scientist"},
        {"id": 3, "title": "Consultor de Educação Internacional Jr"}]}}}
    requested = []

    def transport(request):
        requested.append(str(request.url))
        content = ('<script id="__NEXT_DATA__">' + json.dumps(state) + '</script>'
                   if request.url.path == "/" else page())
        return httpx.Response(200, content=content.encode("utf-8"))

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        records = fetch_gupy_board(client, "example")
    assert len(records) == 1
    assert requested == ["https://example.gupy.io", "https://example.gupy.io/jobs/1"]
