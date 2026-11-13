import httpx
import pytest
from agent.collect_jobs import collect
from agent.iel_jobs import fetch_iel
from agent.job_profile import load_profile

URL = "https://carreiras.iel.org.br/SC/vaga/estagio/123/estagio-sistemas"


def page(local="Trindade", application=True, closed=False):
    sections = {"Empresa:": "Empresa sintética", "Atividades:": "Suporte técnico em sistemas e Python.",
                "Requisitos:": "Cursando ADS.", "Cidade:": "Florianópolis", "Local:": local,
                "Formato de trabalho:": "Presencial"}
    return ("<h1>Estágio em Sistemas</h1>" + "".join(
        f"<h1>{key}</h1><div>{value}</div>" for key, value in sections.items())
        + ('<a href="https://admin-carreiras.sc.iel.org.br/logincandidato.aspx?public-job-id">'
           'Faça login e se candidate</a>' if application else "")
        + ("Vaga encerrada" if closed else "")
        + "<h1>Compartilhe</h1><footer>Rod. Admar Gonzaga, Florianópolis, Itacorubi</footer>")


def client_for(document):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=document)))


def test_iel_uses_vacancy_address_and_passes_through_profile():
    with client_for(page()) as client:
        jobs, report = collect(client, [{"provider": "iel", "url": URL}], profile=load_profile())
    assert len(jobs) == 1
    assert jobs[0]["location"] == "Trindade, Florianópolis, Presencial"
    assert "Rod. Admar" not in jobs[0]["description"]
    assert report["sources"][0]["selected"] == 1


def test_iel_unknown_neighborhood_is_reviewed_without_using_footer_address():
    with client_for(page(local="A confirmar")) as client:
        jobs, report = collect(client, [{"provider": "iel", "url": URL}], profile=load_profile())
    assert jobs == []
    assert len(report["review"]) == 1


def test_iel_closed_is_not_imported():
    with client_for(page(closed=True)) as client:
        assert fetch_iel(client, URL) == []


def test_iel_missing_neighborhood_stays_in_review():
    with client_for(page().replace("<h1>Local:</h1><div>Trindade</div>", "")) as client:
        jobs, report = collect(client, [{"provider": "iel", "url": URL}], profile=load_profile())
    assert jobs == []
    assert len(report["review"]) == 1


def test_iel_not_found_or_closed_notice_is_not_imported():
    with client_for("<h1>Vaga não encontrada ou encerrada!</h1>") as client:
        assert fetch_iel(client, URL) == []


@pytest.mark.parametrize("document", [page(application=False), "<h1>Layout mudou</h1>"])
def test_iel_missing_evidence_fails_explicitly(document):
    with client_for(document) as client, pytest.raises(ValueError):
        fetch_iel(client, URL)


def test_iel_refuses_nonoriginal_url_without_network():
    with client_for(page()) as client, pytest.raises(ValueError):
        fetch_iel(client, "https://example.com/SC/vaga/estagio/123/estagio-sistemas")
