from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.services.llm_client import LLMService
from app.services.resume_tailor import EvidenceValidationError
from app.services.resume_tailor import ResumeTailorService as Service
from main import app
from tests.test_api_routes import JOB, PLAN


def test_ranges_preserve_all_lines_and_keyword_linebreaks():
    raw = "Ana Silva\nPython\nProjeto acadêmico\nSQL"
    plan = {"sections": [{"kind": "perfil", "source_range": [0, 1]},
                         {"kind": "experiencia", "source_range": [2, 3]}],
            "keywords": ["Python", "machine learning"]}
    data = Service.validate_and_render(plan, raw, "Python e machine\nlearning")
    assert "Ana Silva" in data.adapted_resume_markdown
    assert "Projeto acadêmico" in data.adapted_resume_markdown
    assert data.missing_critical_skills == ["machine learning"]
    assert data.match_score == 50
    assert not Service.contains_skill("Java", "JavaScript")


@pytest.mark.parametrize("sections", [
    [{"kind": "perfil", "source_range": [0, 3]}],
    [{"kind": "perfil", "source_range": [True, 1]}],
    [{"kind": "perfil", "source_range": [1, 0]}],
    [{"kind": "perfil", "source_range": [0, 0]}],
    [{"kind": "perfil", "source_range": [0, 1]}, {"kind": "outros", "source_range": [1, 1]}],
    [{"kind": "perfil", "source_range": [0, 1], "source_ids": [0, 1]}],
])
def test_invalid_ranges_are_not_repaired_by_weakening_validation(sections):
    with pytest.raises(EvidenceValidationError):
        Service.validate_and_render({"sections": sections}, "Ana\nPython", "Python")


async def test_one_correction_for_invalid_evidence_then_valid_ranges():
    raw = "Ana\nPython\nSQL"
    valid = {"sections": [{"kind": "perfil", "source_range": [0, 2]}], "keywords": ["Python"]}
    llm = AsyncMock()
    llm.generate_json.side_effect = [
        {"sections": [{"kind": "perfil", "source_ids": [0, 2]}], "keywords": ["Inventado"]}, valid]
    data = await Service.generate_validated(llm, raw, "Python")
    assert llm.generate_json.await_count == 2
    assert "non_contiguous_lines" in llm.generate_json.call_args.args[0]
    assert data.match_score == 100
    assert "Inventado" not in data.adapted_resume_markdown


async def test_invalid_keywords_can_be_corrected_but_never_accepted_without_evidence():
    good = {"sections": [{"kind": "perfil", "source_range": [0, 1]}], "keywords": ["Python"]}
    bad = good | {"keywords": ["Machine Learning"]}
    llm = AsyncMock()
    llm.generate_json.side_effect = [bad, good]
    await Service.generate_validated(llm, "Ana\nPython", "Python")
    assert "keywords_without_job_evidence" in llm.generate_json.call_args.args[0]
    llm.generate_json.side_effect = [bad, bad]
    with pytest.raises(EvidenceValidationError):
        await Service.generate_validated(llm, "Ana\nPython", "Python")
    assert llm.generate_json.await_count == 4


async def test_provider_failure_does_not_trigger_evidence_retry():
    llm = AsyncMock()
    llm.generate_json.side_effect = HTTPException(503, "Provedor indisponível")
    with pytest.raises(HTTPException) as error:
        await Service.generate_validated(llm, "Ana\nPython", "Python")
    assert error.value.status_code == 503
    llm.generate_json.assert_awaited_once()


async def test_correction_timeout_stops_after_one_attempt():
    llm = AsyncMock()
    llm.generate_json.side_effect = [{"sections": []}, TimeoutError()]
    with pytest.raises(HTTPException) as error:
        await Service.generate_validated(llm, "Ana\nPython", "Python")
    assert error.value.status_code == 504
    assert "Nenhuma versão foi salva" in error.value.detail
    assert llm.generate_json.await_count == 2


async def test_first_invalid_response_is_not_saved_and_success_is_cached(mocker, pdf_bytes):
    llm = mocker.patch.object(LLMService, "generate_json", new_callable=AsyncMock, side_effect=[
        {"sections": [{"kind": "perfil", "source_ids": [0, 2]}], "keywords": ["Inventado"]}, PLAN])
    headers = {"X-Resume-Token": "test-evidence-browser-" + "a" * 32}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(2):
            response = await client.post("/api/v1/resumes/tailor", headers=headers,
                                         files={"resume_file": ("synthetic.pdf", pdf_bytes)},
                                         data={"job_description": JOB["description"]})
            assert response.status_code == 200, response.text
        assert response.json()["cached"]
        history = (await client.get("/api/v1/resumes/versions", headers=headers)).json()
        assert len(history) == 1
        assert "Inventado" not in history[0]["data"]["adapted_resume_markdown"]
    assert llm.await_count == 2
