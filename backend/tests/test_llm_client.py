from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import Request, Response
from openai import APIStatusError

from app.core.config import settings
from app.services.llm_client import LLMService


@pytest.mark.parametrize("status,code,expected_status,message", [
    (429, "credit_balance_exhausted", 503, "saldo de créditos"),
    (429, "insufficient_quota", 503, "sem cota"),
    (429, "project_spend_limit_exceeded", 503, "limite de uso"),
    (429, "rate_limit_exceeded", 429, "limite temporário"),
    (401, "invalid_api_key", 503, "chave de API inválida"),
    (403, None, 503, "acesso à API negado"),
    (404, "model_not_found", 503, "modelo indisponível"),
    (400, None, 502, "requisição recusada"),
    (500, None, 503, "temporariamente indisponível"),
])
async def test_provider_error_is_safe_and_actionable(mocker, status, code, expected_status, message):
    mocker.patch.object(settings, "openai_api_key", "fake-secret-must-not-leak")
    response = Response(status, request=Request("POST", "https://api.openai.com"))
    error = APIStatusError("upstream includes fake-secret-must-not-leak and resume text",
                           response=response, body={"error": {"code": code}})
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=error)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    mocker.patch("app.services.llm_client.AsyncOpenAI", return_value=context)
    with pytest.raises(HTTPException) as captured:
        await LLMService().generate_json("texto privado do currículo")
    assert captured.value.status_code == expected_status
    assert message in captured.value.detail
    assert "fake-secret" not in captured.value.detail
    assert "resume text" not in captured.value.detail
    assert "texto privado" not in captured.value.detail


async def test_malformed_json_is_reported(mocker):
    mocker.patch.object(settings, "openai_api_key", "fake")
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(choices=[
        SimpleNamespace(message=SimpleNamespace(content="not json")),
    ]))
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    mocker.patch("app.services.llm_client.AsyncOpenAI", return_value=context)
    with pytest.raises(HTTPException) as captured:
        await LLMService().generate_json("prompt")
    assert captured.value.status_code == 502
    assert "JSON válido" in captured.value.detail
