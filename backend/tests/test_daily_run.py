import json
from datetime import datetime, timezone

import httpx
import pytest
from agent import daily_run, hermes_bridge, runtime, telegram_notify

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
CONFIG = {"INGEST_API_KEY": "synthetic-ingest", "JOB_RADAR_API_URL": "http://127.0.0.1:8000"}
RAW = {"title": "Estágio em Dados", "location": {"name": "Remoto, Brasil"},
       "content": "<p>Desenvolver análises com Python e SQL em dados públicos.</p>",
       "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1"}


@pytest.fixture
def automation(tmp_path, mocker):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent/job_sources.json").write_text(json.dumps([
        {"board": "example", "company": "Empresa teste"}]))
    mocker.patch.object(daily_run, "ROOT", tmp_path)
    mocker.patch.object(daily_run, "RUNTIME", tmp_path / ".runtime")
    notify = mocker.patch.object(daily_run, "send_notification", return_value={"status": "sent", "message_id": 123})
    saved, posts = {}, []

    def transport(request):
        if request.url.host == "boards-api.greenhouse.io":
            return httpx.Response(200, json={"jobs": [RAW]})
        if request.method == "GET":
            return httpx.Response(200, json=list(saved.values()))
        body = json.loads(request.content)
        posts.append(body)
        assert request.headers["X-API-Key"] == CONFIG["INGEST_API_KEY"]
        record = body | {"id": saved.get(body["source_url"], {}).get("id", len(saved) + 1)}
        saved[body["source_url"]] = record
        return httpx.Response(201, json=record)

    original = httpx.Client
    mocker.patch.object(daily_run.httpx, "Client", side_effect=lambda **kwargs:
                        original(transport=httpx.MockTransport(transport), **kwargs))
    return notify, saved, posts


@pytest.mark.parametrize("now,slot", [
    (datetime(2026, 11, 13, 11, 59, tzinfo=timezone.utc), "2026-11-12"),
    (datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc), "2026-11-13"),
    (datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc), "2026-11-13"),
    (datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc), "2026-11-13"),
])
def test_schedule_uses_sao_paulo_and_one_latest_weekday(now, slot):
    assert daily_run.scheduled_slot(now) == slot


def test_daily_search_notifies_once_and_never_generates_resume(automation):
    notify, saved, posts = automation
    report = daily_run.run_once(CONFIG, now=NOW)
    assert report["selected"] == 1 and len(report["new_jobs"]) == 1
    assert report["matched_jobs"] == report["new_jobs"]
    assert report["minimum_results"] == 10
    assert report["meets_target"] is False
    assert report["shortfall"] == 9
    assert "Faltam 9" in daily_run.digest(report)
    assert report["notification_status"] == "sent"
    assert daily_run.run_once(CONFIG, now=NOW)["status"] == "already_completed"
    assert len(posts) == 1 and len(saved) == 1
    assert "/resumes" not in str(posts)
    refreshed = daily_run.run_once(CONFIG, now=NOW, force=True)
    assert refreshed["new_jobs"] == []
    assert len(refreshed["matched_jobs"]) == 1
    assert len(posts) == 2 and len(saved) == 1
    notify.assert_called_once()


def test_ambiguous_telegram_result_is_not_resent(automation):
    notify, _, _ = automation
    notify.side_effect = ValueError("unconfirmed")
    assert daily_run.run_once(CONFIG, now=NOW)["notification_status"] == "unconfirmed"
    assert daily_run.run_once(CONFIG, now=NOW)["status"] == "already_completed"
    assert daily_run.run_once(CONFIG, now=NOW, force=True)["notification_status"] == "unconfirmed"
    notify.assert_called_once()


def test_existing_run_lock_prevents_parallel_search(automation):
    notify, _, posts = automation
    with daily_run.exclusive_run(daily_run.RUNTIME / "daily.lock") as acquired:
        assert acquired
        assert daily_run.run_once(CONFIG, now=NOW)["status"] == "busy"
    assert posts == []
    notify.assert_not_called()


def test_corrupt_state_does_not_resend(automation):
    notify, _, posts = automation
    daily_run.RUNTIME.mkdir()
    (daily_run.RUNTIME / "daily-state.json").write_text("not-json")
    with pytest.raises(ValueError):
        daily_run.run_once(CONFIG, now=NOW)
    notify.assert_not_called()
    assert posts == []


def test_stale_discovery_is_rejected(automation, tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"checked_at": "2020-01-01T00:00:00+00:00", "jobs": []}))
    with pytest.raises(ValueError):
        daily_run.discovery_jobs(path, NOW, daily_run.load_profile())


def test_pending_new_jobs_survive_partial_ingestion_failure(automation):
    notify, _, _ = automation
    daily_run.RUNTIME.mkdir()
    pending = {"id": 25, "title": "Estágio já recebido", "company": "Empresa teste",
               "source_url": "https://example.com/jobs/25"}
    (daily_run.RUNTIME / "daily-state.json").write_text(json.dumps({"pending_new_jobs": [pending]}))
    report = daily_run.run_once(CONFIG, now=NOW)
    assert pending in report["new_jobs"]
    notify.assert_called_once()
    assert "pending_new_jobs" not in daily_run.read_state(daily_run.RUNTIME / "daily-state.json")


def test_runtime_queues_only_the_project_job_once_per_hour(tmp_path, mocker):
    mocker.patch.object(runtime, "RUNTIME", tmp_path)
    (tmp_path / "automation-install.json").write_text(json.dumps({"hermes_job_id": "test-radar-job"}))
    execute = mocker.patch.object(runtime, "checked")
    config = {"JOB_RADAR_HERMES_HOME": "/existing-hermes"}
    assert runtime.queue_due(config, "hermes-test", NOW) == "queued"
    assert runtime.queue_due(config, "hermes-test", NOW) == "recently_queued"
    execute.assert_called_once()
    assert execute.call_args.args[0] == ["hermes-test", "cron", "run", "test-radar-job"]
    assert execute.call_args.kwargs["env"]["HERMES_HOME"] == "/existing-hermes"
    (tmp_path / "daily-state.json").write_text(json.dumps({"completed_slot": "2026-11-13"}))
    assert runtime.queue_due(config, "hermes-test", NOW) == "already_completed"


def test_runtime_failed_dispatch_is_recorded_and_retries_are_bounded(tmp_path, mocker):
    mocker.patch.object(runtime, "RUNTIME", tmp_path)
    (tmp_path / "automation-install.json").write_text(json.dumps({"hermes_job_id": "test-radar-job"}))
    execute = mocker.patch.object(runtime, "checked", side_effect=ValueError("provider unavailable"))
    mocker.patch.object(runtime, "run_once", side_effect=ValueError("network unavailable"))
    config = {"JOB_RADAR_HERMES_HOME": "/existing-hermes"}
    assert runtime.queue_due(config, "hermes-test", NOW) == "unconfirmed"
    assert runtime.queue_due(config, "hermes-test", NOW) == "recently_queued"
    (tmp_path / "runtime-queue.json").write_text(json.dumps({"slot": "2026-11-13",
        "queued_at": "2026-11-13T10:00:00+00:00", "attempts": 3}))
    assert runtime.queue_due(config, "hermes-test", NOW) == "retry_limit_reached"
    execute.assert_called_once()


def test_runtime_has_deterministic_fallback_without_generating_resume(tmp_path, mocker):
    mocker.patch.object(runtime, "RUNTIME", tmp_path)
    (tmp_path / "automation-install.json").write_text(json.dumps({"hermes_job_id": "test-radar-job"}))
    mocker.patch.object(runtime, "checked", side_effect=ValueError("Hermes search unavailable"))
    fallback = mocker.patch.object(runtime, "run_once", return_value={"status": "completed"})
    config = {"JOB_RADAR_HERMES_HOME": "/existing-hermes"}
    assert runtime.queue_due(config, "hermes-test", NOW) == "fallback_completed"
    fallback.assert_called_once_with(config, now=NOW)


def test_successful_bot_generation_sends_only_selected_ids(mocker, monkeypatch):
    for key, value in {"HERMES_SESSION_PLATFORM": "telegram", "HERMES_SESSION_CHAT_TYPE": "dm",
                       "HERMES_SESSION_CHAT_ID": "123", "HERMES_SESSION_ACTOR_ID": "123"}.items():
        monkeypatch.setenv(key, value)
    version = {"id": "v", "job_id": 13, "job_title": "Chosen job", "company": "test",
               "created_at": "2026-11-13", "data": {"match_score": 25}}
    request = mocker.patch.object(hermes_bridge, "api_request", return_value={"version": version, "cached": True})
    result = hermes_bridge.generate_selected({"JOB_RADAR_TELEGRAM_OWNER_ID": "123"}, 13,
                                             "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", True)
    assert result["cached"] and result["sent"] is False
    assert request.call_args.kwargs["payload"] == {
        "job_id": 13, "source_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}


def test_resume_generation_requires_private_request_and_explicit_selection(mocker, monkeypatch):
    config = {"JOB_RADAR_TELEGRAM_OWNER_ID": "123"}
    request = mocker.patch.object(hermes_bridge, "api_request")
    with pytest.raises(PermissionError):
        hermes_bridge.generate_selected(config, 1, "0" * 32, confirmed=True)
    for key, value in {"HERMES_SESSION_PLATFORM": "telegram", "HERMES_SESSION_CHAT_TYPE": "dm",
                       "HERMES_SESSION_CHAT_ID": "123", "HERMES_SESSION_ACTOR_ID": "123"}.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        hermes_bridge.generate_selected(config, 1, "0" * 32)
    request.assert_not_called()


@pytest.mark.parametrize("allowed", ["999", "*", "-123", "user123", "123, *"])
def test_automated_notification_requires_exact_allowed_owner(tmp_path, mocker, allowed):
    (tmp_path / "config.yaml").write_text("{}")
    mocker.patch.object(telegram_notify, "dotenv_values", return_value={
        "TELEGRAM_BOT_TOKEN": "fake-test-token", "TELEGRAM_ALLOWED_USERS": allowed})
    client = mocker.patch.object(telegram_notify.httpx, "Client")
    with pytest.raises(ValueError):
        telegram_notify.send_notification({"JOB_RADAR_TELEGRAM_OWNER_ID": "123",
                                           "JOB_RADAR_HERMES_HOME": str(tmp_path)}, "test only")
    client.assert_not_called()
