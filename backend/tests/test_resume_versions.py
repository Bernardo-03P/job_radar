from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.services.llm_client import LLMService
from main import app
from tests.test_api_routes import JOB, PLAN

TOKEN = "private-browser-token-" + "a" * 32
OTHER_TOKEN = "private-browser-token-" + "b" * 32


async def test_saved_versions_cache_scope_and_deletion(database, mocker, pdf_bytes):
    mocker.patch.object(settings, "ingest_api_key", "ingest-test")
    mocker.patch.object(settings, "resume_api_key", "resume-admin-test")
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock, return_value=PLAN)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job = (await client.post("/api/v1/jobs", json=JOB,
                                 headers={"X-API-Key": "ingest-test"})).json()
        async def generate(description=JOB["description"]):
            return await client.post("/api/v1/resumes/tailor",
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": description, "job_id": job["id"]},
                                     headers={"X-Resume-Token": TOKEN})
        response = await generate()
        assert response.status_code == 200, response.text
        first = response.json()
        assert first["version"]["job_id"] == job["id"]
        assert not first["cached"]
        version_id = first["version"]["id"]
        cached = await generate()
        assert cached.json()["cached"]
        assert cached.json()["version"]["id"] == version_id
        llm.assert_awaited_once()
        assert "owner_hash" not in first["version"]
        assert "pdf_bytes" not in first["version"]
        path = "/api/v1/resumes/versions"
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers={"X-Resume-Token": OTHER_TOKEN})).json() == []
        private = await client.get(path, headers={"X-Resume-Token": TOKEN})
        assert len(private.json()) == 1
        assert private.headers["cache-control"] == "no-store"
        assert (await client.get(path, headers={"X-API-Key": "wrong"})).status_code == 401
        assert len((await client.get(path, headers={"X-API-Key": "resume-admin-test"})).json()) == 1
        assert (await client.get(path + "/" + version_id,
                                 headers={"X-Resume-Token": OTHER_TOKEN})).status_code == 404
        download = await client.get(path + "/" + version_id + "/markdown",
                                    headers={"X-Resume-Token": TOKEN})
        assert download.status_code == 200
        assert "Ana Silva" in download.text
        assert "attachment" in download.headers["content-disposition"]
        changed = await generate(JOB["description"] + " Testes automatizados.")
        assert changed.status_code == 200
        assert changed.json()["version"]["id"] != version_id
        assert llm.await_count == 2
        assert (await client.delete(path + "/" + version_id,
                                    headers={"X-Resume-Token": OTHER_TOKEN})).status_code == 404
        assert (await client.delete(path + "/" + version_id,
                                    headers={"X-Resume-Token": TOKEN})).status_code == 204


async def test_invalid_owner_is_rejected_before_inference(database, mocker, pdf_bytes):
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/resumes/tailor",
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]},
                                     headers={"X-Resume-Token": "short"})
        assert response.status_code == 401
        llm.assert_not_called()
