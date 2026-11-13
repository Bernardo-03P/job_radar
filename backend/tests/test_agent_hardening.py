import json

import pytest
from agent.local_api import local_api_url
from agent.mock_crawler import register_hermes


@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1@evil.com",
                                 "http://user:pass@localhost", "http://localhost/path",
                                 "http://localhost?key=x", "http://localhost#x",
                                 "file:///tmp", "http://localhost:0", "http://localhost:99999"])
def test_external_or_ambiguous_api_is_rejected(url):
    with pytest.raises(ValueError):
        local_api_url(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "http://localhost:8000/", "http://[::1]:8000"])
def test_only_loopback_api_is_accepted(url):
    assert local_api_url(url) == url.rstrip("/")


def test_existing_cron_is_not_registered_twice(tmp_path, mocker):
    (tmp_path / "config.yaml").write_text("{}")
    (tmp_path / "cron").mkdir()
    (tmp_path / "cron/jobs.json").write_text(json.dumps({"jobs": [{"name": "radar"}]}))
    mocker.patch.dict("os.environ", {"HERMES_HOME": str(tmp_path)})
    execute = mocker.patch("agent.mock_crawler.subprocess.run")
    register_hermes({"name": "radar"})
    execute.assert_not_called()


@pytest.mark.parametrize("payload", [None, 1, "invalid", {"jobs": {}}])
def test_invalid_cron_state_fails_closed(tmp_path, mocker, payload):
    (tmp_path / "config.yaml").write_text("{}")
    (tmp_path / "cron").mkdir()
    (tmp_path / "cron/jobs.json").write_text(json.dumps(payload))
    mocker.patch.dict("os.environ", {"HERMES_HOME": str(tmp_path)})
    execute = mocker.patch("agent.mock_crawler.subprocess.run")
    with pytest.raises(ValueError):
        register_hermes({"name": "radar"})
    execute.assert_not_called()
