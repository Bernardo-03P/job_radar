import json
from contextlib import nullcontext

import pytest
from agent import hermes_bridge
from agent import interactive_session as session


@pytest.fixture
def managed(tmp_path, mocker):
    mocker.patch.object(session, 'RUNTIME', tmp_path)
    clock = [1000.0]
    mocker.patch.object(session.time, 'time', side_effect=lambda: clock[0])
    sleep = mocker.patch.object(session.time, 'sleep', side_effect=lambda _: clock.__setitem__(0, clock[0]+60))
    mocker.patch.object(session.runtime, 'executable', return_value='docker')
    db = mocker.patch.object(session, 'container_running', return_value=False)
    api = mocker.patch.object(session.runtime, 'ensure_backend', side_effect=lambda config, on_start: on_start(11))

    def frontend(on_start):
        on_start(22)
        return 'ready'

    site = mocker.patch.object(session.runtime, 'ensure_frontend', side_effect=frontend)
    stop = mocker.patch.object(session, 'stop_backend')
    docker = mocker.patch.object(session.runtime, 'checked')
    return clock, sleep, db, api, site, stop, docker, tmp_path


def test_worker_stops_after_five_minutes_and_closes_owned_resources(managed):
    clock, _, _, _, _, stop, docker, path = managed
    session.worker({})
    assert clock[0] == 1300
    assert [call.args[0] for call in stop.call_args_list] == [22, 11]
    docker.assert_called_once_with(['docker', 'stop', 'job_radar_postgres'], timeout=30)
    assert json.loads((path/'interactive-session.json').read_text())['status'] == 'closed'


def test_web_generation_protects_active_work_and_renews_deadline():
    state = {'last_request_finished': 1000}
    assert not session.expired(state, 1600, {'active': {'synthetic': 1900}})
    assert not session.expired(state, 1600, {'last_finished': 1500})
    assert session.expired(state, 1800, {'last_finished': 1500})


def test_new_formal_request_renews_idle_deadline(managed):
    clock, sleep, _, _, _, _, _, path = managed

    def advance(_):
        clock[0] += 60
        if clock[0] == 1240:
            data = json.loads((path/'interactive-session.json').read_text())
            data['last_request_finished'] = clock[0]
            (path/'interactive-session.json').write_text(json.dumps(data))

    sleep.side_effect = advance
    session.worker({})
    assert clock[0] == 1540


def test_preexisting_manual_services_are_preserved(managed):
    _, _, db, api, site, stop, docker, _ = managed
    db.return_value = True
    api.side_effect = None
    site.side_effect = None
    site.return_value = 'ready'
    session.worker({})
    stop.assert_not_called()
    docker.assert_not_called()


def test_startup_error_still_cleans_owned_resources(managed):
    _, _, _, _, site, stop, docker, path = managed
    site.side_effect = ValueError('synthetic startup failure')
    with pytest.raises(ValueError):
        session.worker({})
    stop.assert_called_once_with(11)
    docker.assert_called_once()
    assert json.loads((path/'interactive-session.json').read_text())['status'] == 'closed'


def test_active_request_prevents_shutdown_even_after_deadline(managed):
    clock, sleep, _, _, _, stop, _, path = managed
    hold = session.exclusive_run(path/'service-use.lock')
    held = [False]

    def advance(_):
        clock[0] += 60
        if not held[0]:
            assert hold.__enter__()
            held[0] = True
        if clock[0] < 1600:
            stop.assert_not_called()
        elif held[0]:
            hold.__exit__(None, None, None)
            held[0] = False

    sleep.side_effect = advance
    session.worker({})
    assert clock[0] == 1600


def test_unauthorized_chat_cannot_start_services(mocker, monkeypatch):
    for key in list(__import__('os').environ):
        if key.startswith('HERMES_SESSION_'):
            monkeypatch.delenv(key)
    monkeypatch.setattr('sys.argv', ['hermes_bridge', 'fontes'])
    mocker.patch.object(hermes_bridge, 'dotenv_values', return_value={'JOB_RADAR_TELEGRAM_OWNER_ID':'123'})
    request = mocker.patch.object(session, 'request_context', return_value=nullcontext())
    with pytest.raises(SystemExit):
        hermes_bridge.main()
    request.assert_not_called()


def test_explicit_local_diagnostic_starts_services_without_calling_ai(mocker, monkeypatch):
    for key in list(__import__('os').environ):
        if key.startswith('HERMES_SESSION_'):
            monkeypatch.delenv(key)
    monkeypatch.setattr('sys.argv', ['hermes_bridge', '--local', 'fontes'])
    mocker.patch.object(hermes_bridge, 'dotenv_values', return_value={'JOB_RADAR_TELEGRAM_OWNER_ID':'123'})
    request = mocker.patch.object(session, 'request_context', return_value=nullcontext())
    api = mocker.patch.object(hermes_bridge, 'api_request', return_value=[])
    hermes_bridge.main()
    request.assert_called_once()
    api.assert_called_once_with({'JOB_RADAR_TELEGRAM_OWNER_ID':'123'}, 'GET', '/api/v1/resumes/sources')
