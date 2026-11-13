import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from sqlalchemy.exc import OperationalError

from app.api.v1.endpoints import resumes
from app.core.config import settings
from app.services import generation_lock as lock_module
from app.services.llm_client import LLMService
from app.services.memory_upload import MemoryFormParser
from app.services.pdf_parser import PDFParserService
from main import app
from tests.test_api_routes import JOB, PLAN

HEADERS = {"X-Resume-Token": "audit-browser-" + "a" * 40}


async def test_unauthenticated_generation_rejected_before_body(mocker):
    parser = mocker.patch.object(MemoryFormParser, "parse", new_callable=AsyncMock)
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/resumes/tailor", content=b"private body")
    assert response.status_code == 401
    parser.assert_not_called()
    llm.assert_not_called()


@pytest.mark.parametrize("body", [
    b"--audit\r\nContent-Disposition: form-data; name=unknown\r\n\r\nx\r\n--audit--\r\n",
    b"--audit\r\nContent-Disposition: form-data; name=job_description\r\n\r\ntruncated",
    b"--audit\r\nContent-Disposition: form-data; name=job_description\r\nContent-Disposition: form-data; name=job_id\r\n\r\nx\r\n--audit--\r\n",
    b"--audit\r\nContent-Disposition: form-data; name=job_description\r\n\r\nx\r\n--audit\r\nContent-Disposition: form-data; name=job_description\r\n\r\ny\r\n--audit--\r\n",
    b"--audit\r\nContent-Disposition: form-data; name=resume_file\r\n\r\nno filename\r\n--audit--\r\n",
])
async def test_malformed_forms_rejected_and_buffers_closed(mocker, body):
    created = []
    original = MemoryFormParser.__init__
    def track(instance):
        original(instance)
        created.append(instance)
    mocker.patch.object(MemoryFormParser, "__init__", track)
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/resumes/tailor", content=body,
                                     headers={**HEADERS, "Content-Type": "multipart/form-data; boundary=audit"})
    assert response.status_code == 400, response.text
    assert all(buffer.closed for parser in created for buffer in parser.buffers)
    llm.assert_not_called()


async def test_slow_upload_times_out(mocker):
    mocker.patch.object(settings, "upload_timeout_seconds", 0.01)
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(0.1)
            yield b"--audit--\r\n"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/resumes/tailor", content=SlowBody(),
                                     headers={**HEADERS, "Content-Type": "multipart/form-data; boundary=audit"})
    assert response.status_code == 408


async def test_concurrent_identical_generation_consumes_ai_once(mocker, pdf_bytes):
    started, release, second = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def generate(prompt):
        started.set()
        await release.wait()
        return PLAN
    llm = mocker.patch.object(LLMService, "generate_json", side_effect=generate)
    original_lock = resumes.generation_lock
    arrivals = 0
    @asynccontextmanager
    async def observe(key):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            second.set()
        async with original_lock(key):
            yield
    mocker.patch.object(resumes, "generation_lock", observe)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async def post():
            return await client.post("/api/v1/resumes/tailor", headers=HEADERS,
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]})
        first = asyncio.create_task(post())
        await asyncio.wait_for(started.wait(), 15)
        other = asyncio.create_task(post())
        try:
            await asyncio.wait_for(second.wait(), 15)
        finally:
            release.set()
        results = await asyncio.gather(first, other)
    assert [result.status_code for result in results] == [200, 200]
    assert results[0].json()["version"]["id"] == results[1].json()["version"]["id"]
    assert results[1].json()["cached"]
    llm.assert_awaited_once()
    assert not lock_module._loops


async def test_concurrency_limit_rejects_excess_upload(mocker, pdf_bytes):
    mocker.patch.object(settings, "max_concurrent_uploads", 1)
    started, release = asyncio.Event(), asyncio.Event()
    async def generate(prompt):
        started.set()
        await release.wait()
        return PLAN
    mocker.patch.object(LLMService, "generate_json", side_effect=generate)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async def post():
            return await client.post("/api/v1/resumes/tailor", headers=HEADERS,
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]})
        first = asyncio.create_task(post())
        await asyncio.wait_for(started.wait(), 15)
        try:
            blocked = await post()
            assert blocked.status_code == 429
            assert blocked.headers["retry-after"] == "5"
        finally:
            release.set()
            await first


async def test_cancelled_lock_waiter_is_removed():
    async with lock_module.generation_lock("key"):
        async def wait():
            async with lock_module.generation_lock("key"):
                pytest.fail("Waiter should have been cancelled")
        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not lock_module._loops


async def test_native_pdf_worker_is_killed_on_timeout(mocker):
    mocker.patch.object(settings, "pdf_timeout_seconds", 0.01)
    worker = MagicMock()
    worker.returncode = None
    async def communicate(data):
        await asyncio.sleep(1)
    worker.communicate = AsyncMock(side_effect=communicate)
    worker.wait = AsyncMock(return_value=-9)
    mocker.patch("app.services.pdf_parser.asyncio.create_subprocess_exec", new_callable=AsyncMock,
                 return_value=worker)
    with pytest.raises(HTTPException) as error:
        await PDFParserService.extract_text_from_pdf(UploadFile(BytesIO(b"%PDF-1.4 synthetic")))
    assert error.value.status_code == 400
    worker.kill.assert_called_once()
    worker.wait.assert_awaited_once()


async def test_database_and_unknown_errors_are_private_json(mocker, pdf_bytes):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        mocker.patch("app.services.resume_store.find_version", side_effect=OperationalError(
            "query", {}, Exception("private-cv-secret")
        ))
        response = await client.post("/api/v1/resumes/tailor", headers=HEADERS,
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]})
        assert response.status_code == 503
        assert "private-cv-secret" not in response.text
        assert response.headers["cache-control"] == "no-store"
        mocker.patch.object(PDFParserService, "extract_text_from_pdf", new_callable=AsyncMock,
                             side_effect=RuntimeError("private-cv-secret"))
        response = await client.post("/api/v1/resumes/tailor",
                                     headers={**HEADERS, "Origin": "http://localhost:3000"},
                                     files={"resume_file": ("cv.pdf", pdf_bytes)},
                                     data={"job_description": JOB["description"]})
        assert response.status_code == 500
        assert response.json() == {"detail": "Erro interno ao processar a solicitação."}
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_unicode_admin_key_is_rejected_without_server_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/resumes/versions",
                                     headers=[(b"x-api-key", "inválida".encode())])
    assert response.status_code == 401


@hypothesis_settings(max_examples=200, deadline=None,
                     suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(payload=st.binary(max_size=1500))
def test_random_multipart_never_leaves_open_buffer(payload):
    parser = MemoryFormParser()
    scope = {"type": "http", "headers": [(b"content-type", b"multipart/form-data; boundary=audit")]}
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    try:
        try:
            asyncio.run(parser.parse(scope, receive))
        except (HTTPException, ValueError):
            pass
    finally:
        parser.close()
    assert all(buffer.closed for buffer in parser.buffers)
