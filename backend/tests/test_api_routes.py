from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from groq import APIConnectionError
from httpx import ASGITransport, AsyncClient, Request

from app.core.config import settings
from app.services.llm_client import LLMService
from app.services.resume_tailor import ResumeTailorService
from main import app

PLAN = {"sections": [{"kind": "perfil", "source_ids": [0, 1, 2]}],
        "keywords": ["Python", "FastAPI", "Docker"]}
JOB = {"title": "Backend Python", "company": "Empresa Exemplo", "location": "Remoto",
       "description": "Desenvolvimento Python com FastAPI e Docker.",
       "source_url": "https://example.com/jobs/backend", "skills": ["Python", "FastAPI"]}


async def test_tailor_success(mocker, pdf_bytes):
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock,
                             return_value=PLAN)
    spool = mocker.patch("starlette.formparsers.SpooledTemporaryFile",
                         side_effect=AssertionError("Disco proibido"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Resume-Token": "test-browser-token-" + "c" * 32}) as client:
        response = await client.post("/api/v1/resumes/tailor",
                                     files={"resume_file": ("test.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["match_score"] == 67
    assert data["missing_critical_skills"] == ["Docker"]
    assert "Empresa Real" in data["adapted_resume_markdown"]
    assert response.headers["cache-control"] == "no-store"
    llm.assert_awaited_once()
    spool.assert_not_called()


async def test_large_valid_pdf_never_spools(mocker, pdf_bytes):
    mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock, return_value=PLAN)
    spool = mocker.patch("starlette.formparsers.SpooledTemporaryFile",
                         side_effect=AssertionError("Disco proibido"))
    payload = pdf_bytes + b"\n" * (2 * 1024 * 1024)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Resume-Token": "test-browser-token-" + "c" * 32}) as client:
        response = await client.post("/api/v1/resumes/tailor",
                                     files={"resume_file": ("cv.pdf", payload)},
                                     data={"job_description": JOB["description"]})
    assert response.status_code == 200, response.text
    spool.assert_not_called()


@pytest.mark.parametrize("filename,payload,status", [
    ("cv.txt", b"texto", 400), ("cv.pdf", b"broken", 400),
    ("cv.pdf", b"x" * (5 * 1024 * 1024 + 1), 400),
    ("cv.pdf", b"x" * (6 * 1024 * 1024), 413),
])
async def test_reject_bad_upload(mocker, filename, payload, status):
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Resume-Token": "test-browser-token-" + "c" * 32}) as client:
        response = await client.post("/api/v1/resumes/tailor",
                                     files={"resume_file": (filename, payload)},
                                     data={"job_description": JOB["description"]})
    assert response.status_code == status
    llm.assert_not_called()


async def test_reject_hallucination(mocker, pdf_bytes):
    mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock, return_value={
        "sections": [{"kind": "perfil", "source_ids": [0, 1, 999]}], "keywords": []
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Resume-Token": "test-browser-token-" + "c" * 32}) as client:
        response = await client.post("/api/v1/resumes/tailor",
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]})
    assert response.status_code == 502


@pytest.mark.parametrize("plan", [
    {"sections": [{"kind": "perfil", "source_ids": [0]}]},
    {"sections": [{"kind": "perfil", "source_ids": [0, 0, 1]}]},
    {"sections": [{"kind": "perfil", "source_ids": [0, 1]}], "keywords": ["Inventado"]},
    {"sections": [{"kind": "perfil", "source_ids": [1, 0]}]},
])
def test_evidence_validation(plan):
    with pytest.raises(HTTPException):
        ResumeTailorService.validate_and_render(plan, "Ana\nPython", JOB["description"])


async def test_jobs_ingestion_and_list(database, mocker):
    mocker.patch.object(settings, "ingest_api_key", "test-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Resume-Token": "test-browser-token-" + "c" * 32}) as client:
        assert (await client.post("/api/v1/jobs", json=JOB)).status_code == 401
        created = await client.post("/api/v1/jobs", json=JOB, headers={"X-API-Key": "test-secret"})
        assert created.status_code == 201, created.text
        duplicate = await client.post("/api/v1/jobs", json=JOB, headers={"X-API-Key": "test-secret"})
        assert duplicate.json()["id"] == created.json()["id"]
        listed = await client.get("/api/v1/jobs?q=Python")
        assert len(listed.json()) == 1
        assert (await client.get("/api/v1/jobs?limit=0")).status_code == 422


async def test_llm_no_keys():
    with pytest.raises(HTTPException) as error:
        await LLMService().generate_json("prompt")
    assert error.value.status_code == 503


def test_keyword_boundaries():
    assert not ResumeTailorService.contains_skill("Java", "JavaScript")
    assert not ResumeTailorService.contains_skill("SQL", "PostgreSQL")
    assert ResumeTailorService.contains_skill("C++", "Experiência em C++ e Python")


async def test_missing_keys_returns_json(pdf_bytes):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Resume-Token": "test-browser-token-" + "c" * 32}) as client:
        response = await client.post("/api/v1/resumes/tailor",
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]},
                                     headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "Configure" in response.json()["detail"]


async def test_llm_fallback(mocker):
    mocker.patch.object(settings, "groq_api_key", "fake-groq")
    mocker.patch.object(settings, "openai_api_key", "fake-openai")
    groq = MagicMock()
    groq.chat.completions.create = AsyncMock(side_effect=APIConnectionError(
        request=Request("POST", "https://api.groq.com")
    ))
    openai = MagicMock()
    openai.chat.completions.create = AsyncMock(return_value=SimpleNamespace(choices=[
        SimpleNamespace(message=SimpleNamespace(content='{"sections": []}'))
    ]))
    for name, client in [("AsyncGroq", groq), ("AsyncOpenAI", openai)]:
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        mocker.patch("app.services.llm_client." + name, return_value=context)
    assert await LLMService().generate_json("prompt") == {"sections": []}
    openai.chat.completions.create.assert_awaited_once()
