import httpx
import pytest
from agent.collect_jobs import collect, description_text, normalize_job
from backend.app.schemas.job import canonical_source_url

SOURCES = [{"board": "example", "company": "Empresa de teste"}]


def vacancy(**changes):
    return {"title": "Backend Software Engineer", "location": {"name": "Brasil"},
            "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1",
            "content": "&lt;p&gt;Desenvolver APIs com Python e PostgreSQL.&lt;/p&gt;"} | changes


def client_for(payload, status=200):
    return httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json=payload)), follow_redirects=False)


def test_extracts_facts_without_inventing_remote_or_skills():
    job = normalize_job(vacancy(location={}), "Empresa de teste")
    assert job["location"] == "Não informada pela fonte"
    assert job["skills"] == ["Python", "PostgreSQL"]
    assert job["description"] == "Desenvolver APIs com Python e PostgreSQL."


def test_decodes_html_and_removes_script_and_style():
    assert description_text("&lt;p&gt;Python &amp; SQL&lt;/p&gt;<script>bad</script>"
                            "<style>hidden</style>") == "Python & SQL"


@pytest.mark.parametrize("changes", [{"content": ""}, {"content": "short"},
                                   {"absolute_url": "http://example.com/jobs/1"},
                                   {"absolute_url": "https://user:pass@example.com/job"}])
def test_rejects_missing_evidence_or_bad_original_link(changes):
    with pytest.raises(ValueError):
        normalize_job(vacancy(**changes), "Empresa de teste")


def test_filters_deduplicates_and_reports_invalid_records():
    with client_for({"jobs": [vacancy(), vacancy(), vacancy(title="Accountant"),
                              vacancy(content=""), None]}) as client:
        jobs, report = collect(client, SOURCES, query="Python", location="Brasil")
    assert len(jobs) == 1
    assert report["sources"][0]["received"] == 5
    assert report["sources"][0]["invalid"] == 2
    assert report["sources"][0]["filtered"] == 1


def test_zero_matches_is_empty_without_fixtures():
    with client_for({"jobs": [vacancy()]}) as client:
        assert collect(client, SOURCES, location="Canada")[0] == []


@pytest.mark.parametrize("status,payload", [(429, {}), (500, {}), (302, {}),
                                          (200, {"jobs": {}})])
def test_source_failure_is_not_treated_as_success(status, payload):
    with client_for(payload, status) as client:
        with pytest.raises((httpx.HTTPStatusError, ValueError)):
            collect(client, SOURCES)


def test_collection_limit_and_invalid_board():
    second = vacancy(absolute_url="https://job-boards.greenhouse.io/example/jobs/2")
    with client_for({"jobs": [vacancy(), second]}) as client:
        assert len(collect(client, SOURCES, limit=1)[0]) == 1
        with pytest.raises(ValueError):
            collect(client, [{"board": "../../bad", "company": "bad"}])


def test_tracking_parameters_do_not_duplicate_jobs_and_indeed_id_is_preserved():
    assert canonical_source_url("https://br.indeed.com/viewjob?jk=abc123&utm_source=search") == (
        "https://br.indeed.com/viewjob?jk=abc123")
    with client_for({"jobs": [vacancy(), vacancy(absolute_url=(
            "https://job-boards.greenhouse.io/example/jobs/1?jobBoardSource=gupy_public_page&utm_campaign=test"))]}) as client:
        assert len(collect(client, SOURCES)[0]) == 1
