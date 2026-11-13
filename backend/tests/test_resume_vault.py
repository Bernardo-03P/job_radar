import os
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services import resume_vault
from app.services.llm_client import LLMService
from app.services.memory_upload import MemoryFormParser
from main import app
from tests.test_api_routes import JOB, PLAN

TOKEN = "source-browser-" + "a" * 40
OTHER = "source-browser-" + "b" * 40


@pytest.fixture
def vault(tmp_path, mocker):
    mocker.patch.object(resume_vault, "VAULT", tmp_path / "vault")
    mocker.patch.object(resume_vault, "protect", side_effect=lambda data, decrypt=False:
                        bytes(byte ^ 0x5A for byte in data))
    mocker.patch.object(settings, "resume_api_key", "test-private-key")
    return resume_vault.VAULT


def test_source_scope_replace_and_delete(vault, pdf_bytes):
    first = resume_vault.save_source(pdf_bytes, "../fake.pdf", TOKEN)
    assert first["filename"] == "fake.pdf"
    path = resume_vault.source_path(first["id"])
    assert pdf_bytes not in path.read_bytes()
    assert TOKEN.encode() not in path.read_bytes()
    assert "token" not in first and "pdf" not in first
    assert resume_vault.list_sources(OTHER) == []
    with pytest.raises(HTTPException) as error:
        resume_vault.read_source(first["id"], OTHER)
    assert error.value.status_code == 404
    replaced = resume_vault.save_source(pdf_bytes, "new.pdf", TOKEN)
    assert replaced["id"] == first["id"]
    assert len(list(vault.glob("*.bin"))) == 1
    assert len(resume_vault.list_sources(api_key="test-private-key")) == 1
    resume_vault.delete_source(first["id"], TOKEN)
    assert resume_vault.list_sources(TOKEN) == []


@pytest.mark.parametrize("identifier", ["../private", "file:///secret", "not-a-uuid"])
def test_source_paths_reject_traversal(vault, identifier):
    with pytest.raises(HTTPException):
        resume_vault.source_path(identifier)


async def test_source_upload_requires_auth_before_parsing(vault, mocker):
    parser = mocker.patch.object(MemoryFormParser, "parse", new_callable=AsyncMock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/resumes/sources", content=b"private content")
    assert response.status_code == 401
    parser.assert_not_called()


async def test_saved_source_generation_uses_chosen_job_cache_and_ownership(vault, mocker, pdf_bytes):
    mocker.patch.object(settings, "ingest_api_key", "test-ingest")
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock, return_value=PLAN)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        upload = await client.post("/api/v1/resumes/sources", headers={"X-Resume-Token": TOKEN},
                                   files={"resume_file": ("synthetic.pdf", pdf_bytes)})
        assert upload.status_code == 201, upload.text
        assert upload.headers["cache-control"] == "no-store"
        source = upload.json()
        llm.assert_not_awaited()
        saved_job = (await client.post("/api/v1/jobs", json=JOB,
                                      headers={"X-API-Key": "test-ingest"})).json()
        payload = {"source_id": source["id"], "job_id": saved_job["id"]}
        assert (await client.post("/api/v1/resumes/tailor-saved", json=payload)).status_code == 401
        result = await client.post("/api/v1/resumes/tailor-saved", json=payload,
                                   headers={"X-API-Key": "test-private-key"})
        assert result.status_code == 200, result.text
        assert result.json()["version"]["job_id"] == saved_job["id"]
        assert not result.json()["cached"]
        again = await client.post("/api/v1/resumes/tailor-saved", json=payload,
                                  headers={"X-API-Key": "test-private-key"})
        assert again.json()["cached"]
        llm.assert_awaited_once()
        private_history = await client.get("/api/v1/resumes/versions", headers={"X-Resume-Token": TOKEN})
        assert len(private_history.json()) == 1
        assert (await client.get("/api/v1/resumes/versions", headers={"X-Resume-Token": OTHER})).json() == []
        assert (await client.delete("/api/v1/resumes/sources/" + source["id"],
                                    headers={"X-Resume-Token": OTHER})).status_code == 404
        assert (await client.delete("/api/v1/resumes/sources/" + source["id"],
                                    headers={"X-Resume-Token": TOKEN})).status_code == 204
        assert len((await client.get("/api/v1/resumes/versions", headers={"X-Resume-Token": TOKEN})).json()) == 1


async def test_missing_job_or_source_cannot_call_inference(vault, mocker, pdf_bytes):
    source = resume_vault.save_source(pdf_bytes, "synthetic.pdf", TOKEN)
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for source_id in (source["id"], str(uuid4())):
            result = await client.post("/api/v1/resumes/tailor-saved",
                                       json={"source_id": source_id, "job_id": 999},
                                       headers={"X-API-Key": "test-private-key"})
            assert result.status_code == 404
    llm.assert_not_awaited()


async def test_saved_generation_rejects_unauthorized_or_oversized_body_before_inference(vault, mocker):
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        unauthorized = await client.post("/api/v1/resumes/tailor-saved", content=b"private" * 10000,
                                         headers={"Content-Type": "application/json"})
        assert unauthorized.status_code == 401
        large = await client.post("/api/v1/resumes/tailor-saved", content=b" " * 5000,
                                  headers={"Content-Type": "application/json", "X-API-Key": "test-private-key"})
        assert large.status_code == 413
        invalid = await client.post("/api/v1/resumes/tailor-saved", content=b"not-json",
                                    headers={"Content-Type": "text/plain", "X-API-Key": "test-private-key"})
        assert invalid.status_code == 415
    llm.assert_not_awaited()


async def test_saved_generation_rejects_chunked_overflow_and_batch(vault, mocker):
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock)

    async def chunks():
        yield b" " * 3000
        yield b" " * 2000

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-API-Key": "test-private-key", "Content-Type": "application/json"}
        result = await client.post("/api/v1/resumes/tailor-saved", content=chunks(), headers=headers)
        assert result.status_code == 413
        batch = await client.post("/api/v1/resumes/tailor-saved", json={
            "source_id": str(uuid4()), "job_id": [1, 2, 3]}, headers=headers)
        assert batch.status_code == 422
    llm.assert_not_awaited()


@pytest.mark.skipif(os.name != "nt", reason="DPAPI disponível somente no Windows")
def test_real_windows_dpapi_roundtrip_and_tampering():
    plain = b"Synthetic PDF bytes only; no personal documents"
    encrypted = resume_vault.protect(plain)
    assert plain not in encrypted
    assert resume_vault.protect(encrypted, decrypt=True) == plain
    with pytest.raises(HTTPException):
        resume_vault.protect(encrypted[:-10] + b"corrupted!", decrypt=True)
