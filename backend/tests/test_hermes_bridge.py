from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from agent import hermes_bridge

OWNER = "123456789"
CONFIG = {"JOB_RADAR_TELEGRAM_OWNER_ID": OWNER, "RESUME_API_KEY": "private-test-key",
          "JOB_RADAR_HERMES_HOME": "/hermes-test"}
PRIVATE = {"HERMES_SESSION_PLATFORM": "telegram", "HERMES_SESSION_CHAT_TYPE": "dm",
           "HERMES_SESSION_CHAT_ID": OWNER, "HERMES_SESSION_USER_ID": OWNER,
           "HERMES_SESSION_ACTOR_ID": OWNER}


@pytest.mark.parametrize("change", [
    {"HERMES_SESSION_PLATFORM": "discord"}, {"HERMES_SESSION_CHAT_TYPE": "group"},
    {"HERMES_SESSION_CHAT_ID": "999"}, {"HERMES_SESSION_ACTOR_ID": "999"},
    {"HERMES_SESSION_CHAT_ID": "-123"}, {"HERMES_SESSION_PLATFORM": ""},
])
def test_private_resume_access_rejects_other_contexts(change):
    with pytest.raises(PermissionError):
        hermes_bridge.require_private_context(CONFIG, PRIVATE | change)
    with pytest.raises(PermissionError):
        hermes_bridge.require_private_context(CONFIG, PRIVATE | change, local=True)


def test_private_context_accepts_only_owner_or_explicit_local():
    hermes_bridge.require_private_context(CONFIG, PRIVATE)
    hermes_bridge.require_private_context(CONFIG, {}, local=True)
    with pytest.raises(PermissionError):
        hermes_bridge.require_private_context(CONFIG, {})


def test_api_key_is_never_sent_to_external_host(mocker):
    client = mocker.patch.object(httpx, "Client")
    with pytest.raises(ValueError):
        hermes_bridge.api_request(CONFIG | {"JOB_RADAR_API_URL": "https://example.com"}, "GET", "/health")
    client.assert_not_called()


def test_telegram_document_uses_memory_and_fixed_private_destination(mocker, monkeypatch):
    for key, value in PRIVATE.items():
        monkeypatch.setenv(key, value)
    mocker.patch.object(hermes_bridge, "dotenv_values", return_value={"TELEGRAM_BOT_TOKEN": "test-token"})
    version = {"id": "synthetic-id", "job_title": "Vaga de teste",
               "data": {"adapted_resume_markdown": "# Candidata fictícia\nPython"}}

    def inspect_request(url, **kwargs):
        assert url == "https://api.telegram.org/bottest-token/sendDocument"
        assert kwargs["data"]["chat_id"] == OWNER
        filename, document, media = kwargs["files"]["document"]
        assert isinstance(document, BytesIO)
        assert filename == "curriculo-synthetic-id.md"
        assert media == "text/markdown"
        assert "Candidata fictícia" in document.getvalue().decode()
        return SimpleNamespace(is_success=True, json=lambda: {"ok": True})

    client = MagicMock()
    client.__enter__.return_value = client
    client.post.side_effect = inspect_request
    mocker.patch.object(httpx, "Client", return_value=client)
    assert hermes_bridge.send_document(CONFIG, version)["status"] == "sent"
    client.post.assert_called_once()


def test_telegram_failure_never_exposes_bot_token(mocker, monkeypatch):
    for key, value in PRIVATE.items():
        monkeypatch.setenv(key, value)
    mocker.patch.object(hermes_bridge, "dotenv_values", return_value={"TELEGRAM_BOT_TOKEN": "private-secret"})
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.side_effect = httpx.ConnectError("URL contains private-secret")
    mocker.patch.object(httpx, "Client", return_value=client)
    with pytest.raises(ValueError) as error:
        hermes_bridge.send_document(CONFIG, {"id": "test", "job_title": "Teste",
                                             "data": {"adapted_resume_markdown": "Texto sintético"}})
    assert "private-secret" not in str(error.value)


def test_manual_search_requires_private_telegram_context(mocker):
    execute = mocker.patch.object(hermes_bridge.subprocess, "run")
    with pytest.raises(PermissionError):
        hermes_bridge.search_now(CONFIG)
    execute.assert_not_called()


def test_manual_search_forces_refresh_without_duplicate_notification(mocker, monkeypatch):
    for key, value in PRIVATE.items():
        monkeypatch.setenv(key, value)
    execute = mocker.patch.object(hermes_bridge.subprocess, "run", return_value=SimpleNamespace(
        returncode=0, stdout='{"status":"completed","selected":2,"new_jobs":[]}'))
    result = hermes_bridge.search_now(CONFIG, include_discovery=True)
    arguments = execute.call_args.args[0]
    assert "--run-now" in arguments and "--no-notify" in arguments
    assert arguments[-1].endswith("telegram-candidates.json")
    assert execute.call_args.kwargs["cwd"] == hermes_bridge.ROOT
    assert result["reply_in_current_chat"] and not result["automatic_notification"]


def test_manual_search_error_omits_subprocess_output(mocker, monkeypatch):
    for key, value in PRIVATE.items():
        monkeypatch.setenv(key, value)
    mocker.patch.object(hermes_bridge.subprocess, "run", return_value=SimpleNamespace(
        returncode=1, stdout="private-subprocess-detail"))
    with pytest.raises(ValueError) as error:
        hermes_bridge.search_now(CONFIG)
    assert "private-subprocess-detail" not in str(error.value)
