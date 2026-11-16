"""Coleta vagas publicadas na API pública Greenhouse, sem inferência de IA."""
import argparse
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from backend.app.schemas.job import JobCreate

from .iel_jobs import fetch_iel
from .job_profile import load_profile, prioritize, profile_match
from .public_jobs import fetch_gupy, fetch_gupy_board

ROOT = Path(__file__).resolve().parents[1]
API = "https://boards-api.greenhouse.io/v1/boards"
TECH = re.compile(
    r"software|backend|back.end|front.end|full.stack|devops|sre\b|"
    r"data (engineer|scien|analy)|engenh\w* de dados|"
    r"desenvolv|machine learning|security engineer|quality engineer|qa\b", re.I
)
SKILLS = ("Python", "SQL", "PostgreSQL", "Docker", "FastAPI", "Java", "JavaScript",
          "TypeScript", "React", "Kubernetes", "AWS", "GCP", "Azure", "Go", "Scala")


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "div", "li", "br", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def description_text(content):
    parser = PlainText()
    parser.feed(html.unescape(content))
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines()
                     if line.strip())


def normalize_job(raw, company):
    if not isinstance(raw, dict):
        raise ValueError("Registro inválido")
    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Descrição ausente")
    url = raw.get("absolute_url", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Link original inválido")
    description = description_text(content)
    location = raw.get("location") or {}
    return JobCreate(
        title=raw.get("title"), company=company,
        location=location.get("name") or "Não informada pela fonte",
        description=description, source_url=url,
        skills=[skill for skill in SKILLS
                if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", description, re.I)],
    ).model_dump(mode="json")


def collect(client, sources, query="", location="", limit=50, profile=None):
    if not isinstance(sources, list) or not sources:
        raise ValueError("Configure ao menos uma fonte Greenhouse.")
    if not 1 <= limit <= 500:
        raise ValueError("O limite precisa estar entre 1 e 500.")
    jobs, reports, seen, review = [], [], set(), []
    for source in sources:
        provider = source.get("provider", "greenhouse")
        if provider not in ("gupy", "gupy_board", "greenhouse", "iel"):
            raise ValueError("Provedor de vagas não suportado.")
        if provider == "gupy_board":
            board = source["board"]
            records = fetch_gupy_board(client, board)
            endpoint = f"https://{board}.gupy.io"
        elif provider in ("gupy", "iel"):
            endpoint = source["url"]
            records = fetch_gupy(client, endpoint) if provider == "gupy" else fetch_iel(client, endpoint)
            board = provider
        else:
            board, company = source["board"], source["company"]
            if not re.fullmatch(r"[a-z0-9_-]{1,100}", board):
                raise ValueError("Identificador de board inválido.")
            endpoint = f"{API}/{board}/jobs"
            response = client.get(endpoint, params={"content": "true"})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                raise ValueError("A fonte retornou um formato inesperado.")
            records = [(raw, company) for raw in payload["jobs"]]
        report = {"board": board, "endpoint": endpoint, "received": len(records),
                  "invalid": 0, "filtered": 0, "eligible": 0, "reasons": {}, "urls": []}
        for raw, company in records:
            try:
                job = normalize_job(raw, company)
            except (ValueError, TypeError, AttributeError):
                report["invalid"] += 1
                continue
            if ((profile is None and not TECH.search(job["title"]))
                    or query.casefold() not in (job["title"] + " " + job["description"]).casefold()
                    or location.casefold() not in job["location"].casefold()):
                report["filtered"] += 1
                continue
            if profile is not None:
                matched, reason = profile_match(job, profile)
                if not matched:
                    report["filtered"] += 1
                    report["reasons"][reason] = report["reasons"].get(reason, 0) + 1
                    if reason in ("florianopolis_bairro_a_confirmar", "regiao_sem_endereco_confirmado",
                                  "local_ou_elegibilidade_nao_confirmado", "n2_exige_experiencia_revisar",
                                  "horario_nao_confirmado", "horario_alternativas_a_confirmar"):
                        review.append({"reason": reason, "job": job})
                    continue
            if job["source_url"] in seen:
                continue
            seen.add(job["source_url"])
            jobs.append(job)
            report["eligible"] += 1
            report["urls"].append(job["source_url"])
        reports.append(report)
    jobs = jobs[:limit] if profile is None else prioritize(jobs, limit, profile)
    selected_urls = {job["source_url"] for job in jobs}
    for report in reports:
        report["selected"] = sum(url in selected_urls for url in report.pop("urls"))
    return jobs, {"checked_at": datetime.now(timezone.utc).isoformat(), "sources": reports,
                  "query": query, "location": location, "limit": limit, "selected": len(jobs),
                  "profile_applied": profile is not None, "review": review}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="", help="Trecho literal no título ou descrição")
    parser.add_argument("--location", default="", help="Trecho literal da localização da fonte")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    try:
        sources = json.loads((ROOT / "agent/job_sources.json").read_text(encoding="utf-8"))
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False,
                          headers={"User-Agent": "JobRadar/1.0 (personal job search)"}) as client:
            jobs, report = collect(client, sources, args.query, args.location, args.limit,
                                   profile=load_profile())
        review = report.pop("review")
        report["review_count"] = len(review)
        write_json(ROOT / "agent/collected_jobs.json", jobs)
        write_json(ROOT / ".runtime/collection-report.json", report)
        write_json(ROOT / ".runtime/collection-review.json", review)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError):
        parser.exit(1, "Coleta falhou. Confira conexão, fontes e permissões; não importe o arquivo anterior.\n")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not jobs:
        parser.exit(2, "Nenhuma vaga correspondeu aos filtros; nenhuma vaga fictícia foi criada.\n")


if __name__ == "__main__":
    main()
