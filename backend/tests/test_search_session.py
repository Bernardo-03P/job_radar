import json
from datetime import datetime, timezone

import pytest
from agent import daily_run, search_session

NOW = datetime(2026, 11, 13, 15, tzinfo=timezone.utc)


@pytest.fixture
def session(tmp_path, mocker):
    mocker.patch.object(search_session, "RUNTIME", tmp_path)
    mocker.patch.object(daily_run, "RUNTIME", tmp_path)
    mocker.patch.object(search_session.runtime, "executable", return_value="docker")
    database = mocker.patch.object(search_session, "container_running", return_value=False)
    ready = mocker.patch.object(search_session.runtime, "backend_ready", return_value=False)
    start = mocker.patch.object(search_session.runtime, "ensure_backend",
                               side_effect=lambda config, on_start: on_start(12345))
    stop = mocker.patch.object(search_session, "stop_backend")
    command = mocker.patch.object(search_session.runtime, "checked")
    run = mocker.patch.object(daily_run, "run_once", return_value={"status": "completed"})
    return database, ready, start, stop, command, run, tmp_path


def test_search_starts_and_stops_only_its_services(session):
    _, _, start, stop, command, run, path = session
    assert search_session.run_session({}, now=NOW) == {"status": "completed"}
    start.assert_called_once()
    stop.assert_called_once_with(12345)
    command.assert_called_once_with(["docker", "stop", "job_radar_postgres"], timeout=30)
    run.assert_called_once()
    assert json.loads((path / "search-session.json").read_text())["status"] == "closed"


def test_collection_failure_still_stops_services(session):
    _, _, _, stop, command, run, _ = session
    run.side_effect = ValueError("synthetic failure")
    with pytest.raises(ValueError):
        search_session.run_session({}, now=NOW)
    stop.assert_called_once_with(12345)
    command.assert_called_once()


def test_startup_failure_still_stops_owned_backend_and_database(session):
    _, _, start, stop, command, run, _ = session

    def fail(config, on_start):
        on_start(12345)
        raise ValueError("backend readiness failed")

    start.side_effect = fail
    with pytest.raises(ValueError):
        search_session.run_session({}, now=NOW)
    stop.assert_called_once()
    command.assert_called_once()
    run.assert_not_called()


def test_services_opened_by_owner_are_preserved(session):
    database, ready, start, stop, command, _, _ = session
    database.return_value = ready.return_value = True
    search_session.run_session({}, now=NOW)
    start.assert_not_called()
    stop.assert_not_called()
    command.assert_not_called()


def test_completed_scheduled_search_does_not_start_anything(session):
    database, _, start, _, _, run, path = session
    (path / "daily-state.json").write_text(json.dumps({"completed_slot": "2026-11-13"}))
    assert search_session.run_session({}, now=NOW)["status"] == "already_completed"
    database.assert_not_called()
    start.assert_not_called()
    run.assert_not_called()


def test_cleanup_failure_is_reported_and_database_stop_is_still_attempted(session):
    _, _, _, stop, command, _, path = session
    stop.side_effect = ValueError("stop failed")
    with pytest.raises(ValueError, match="desligamento"):
        search_session.run_session({}, now=NOW)
    command.assert_called_once()
    assert json.loads((path / "search-session.json").read_text())["cleanup_errors"] == ["backend"]
