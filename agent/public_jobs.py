"""Leitura de JobPosting publicado em páginas públicas da Gupy, sem autenticação."""
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

from .job_profile import stage


class StructuredJobs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []
        self.blocks = []
        self.state_blocks = []
        self.kind = "ld"
        self.hidden = False
        self.visible = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden = True
        attributes = dict(attrs)
        if tag == "script" and (attributes.get("type") == "application/ld+json"
                                or attributes.get("id") == "__NEXT_DATA__"):
            self.capture = True
            self.kind = "next" if attributes.get("id") == "__NEXT_DATA__" else "ld"
            self.parts = []

    def handle_data(self, value):
        if self.capture:
            self.parts.append(value)
        if not self.hidden:
            self.visible.append(value)

    def handle_endtag(self, tag):
        if tag == "script" and self.capture:
            target = self.state_blocks if self.kind == "next" else self.blocks
            target.append("".join(self.parts))
            self.capture = False
        if tag in ("script", "style"):
            self.hidden = False


def postings(value):
    if isinstance(value, list):
        for item in value:
            yield from postings(item)
    elif isinstance(value, dict):
        if value.get("@type") == "JobPosting":
            yield value
        if "@graph" in value:
            yield from postings(value["@graph"])


def fetch_gupy(client, url):
    if not re.fullmatch(r"https://[a-z0-9-]+\.gupy\.io/jobs/[0-9]+", url):
        raise ValueError("Configure somente links públicos originais de vagas Gupy.")
    response = client.get(url)
    response.raise_for_status()
    document = response.content.decode("utf-8")
    parser = StructuredJobs()
    parser.feed(document)
    if re.search(r"vaga (?:encerrada|indispon[ií]vel)|inscri[çc][oõ]es encerradas|"
                 r"applications closed|job (?:closed|unavailable)",
                 " ".join(parser.visible), re.I):
        return []
    for block in parser.blocks:
        try:
            data = json.loads(block)
        except ValueError:
            data = json.loads(html.unescape(block))
        for item in postings(data):
            if item.get("validThrough"):
                deadline = datetime.fromisoformat(item["validThrough"].replace("Z", "+00:00"))
                if deadline.date() < datetime.now(timezone.utc).date():
                    return []
            place = item.get("jobLocation") or {}
            if isinstance(place, list):
                if len(place) != 1:
                    raise ValueError("Vaga com múltiplos endereços exige revisão.")
                place = place[0]
            address = place.get("address") or {}
            location = ", ".join(str(address[key]) for key in
                                 ("streetAddress", "addressLocality", "addressRegion", "addressCountry")
                                 if address.get(key))
            mode = place.get("additionalProperty") or {}
            if (item.get("jobLocationType") == "TELECOMMUTE"
                    or isinstance(mode, dict) and mode.get("value") == "TELECOMMUTE"):
                location = "Remoto, " + location
            raw = {"title": item.get("title"), "content": item.get("description"),
                   "absolute_url": url, "location": {"name": location}}
            company = item.get("hiringOrganization", {}).get("name")
            return [(raw, company)]
    # Algumas páginas públicas usam somente o estado Next, exibido no próprio HTML.
    for block in parser.state_blocks:
        job = json.loads(block).get("props", {}).get("pageProps", {}).get("job")
        if not isinstance(job, dict):
            continue
        board = url.split("/")[2].split(".")[0]
        if (job.get("id") != int(url.rsplit("/", 1)[1])
                or job.get("company", {}).get("subdomain") != board):
            raise ValueError("Estado público não corresponde ao anúncio original.")
        if job.get("status") != "published" or job.get("publicationType") != "external":
            return []
        for field in ("expiresAt", "registerEndDate"):
            if job.get(field):
                deadline = datetime.fromisoformat(job[field].replace("Z", "+00:00"))
                if deadline.date() < datetime.now(timezone.utc).date():
                    return []
        parts = [job.get(key) for key in ("description", "responsibilities", "prerequisites", "relevantExperiences")]
        if not all(isinstance(part, str) for part in parts):
            raise ValueError("Descrição pública incompleta; revise a fonte.")
        location = ", ".join(str(job[key]) for key in
                             ("addressLine", "addressCity", "addressState", "addressCountry") if job.get(key))
        mode = {"remote": "Remoto", "hybrid": "Híbrido", "on-site": "Presencial"}.get(job.get("workplaceType"))
        if mode:
            location = mode + ", " + location
        company = job.get("careerPage", {}).get("name")
        if not company:
            raise ValueError("Empresa não informada na página original.")
        return [({"title": job.get("name"), "content": "\n".join(parts),
                  "absolute_url": url, "location": {"name": location}}, company)]
    raise ValueError("Página sem JobPosting ou estado público verificável.")


def fetch_gupy_board(client, board):
    if not re.fullmatch(r"[a-z0-9-]{1,100}", board):
        raise ValueError("Identificador de empresa Gupy inválido.")
    origin = f"https://{board}.gupy.io"
    response = client.get(origin)
    response.raise_for_status()
    parser = StructuredJobs()
    parser.feed(response.content.decode("utf-8"))
    if not parser.state_blocks:
        raise ValueError("Página de carreiras sem lista pública verificável.")
    payload = json.loads(parser.state_blocks[0])
    vacancies = payload.get("props", {}).get("pageProps", {}).get("jobs")
    if not isinstance(vacancies, list):
        raise ValueError("Formato da página de carreiras mudou; revise a integração.")
    records, seen = [], set()
    for item in vacancies:
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            raise ValueError("Lista pública contém registro inesperado.")
        if not stage({"title": item["title"]}):
            continue
        identifier = item.get("id")
        if type(identifier) is not int or identifier <= 0:
            raise ValueError("Identificador de vaga pública inválido.")
        if identifier in seen:
            continue
        seen.add(identifier)
        if len(seen) > 50:
            raise ValueError("Mais de 50 vagas de entrada na fonte; refine antes de coletar.")
        records.extend(fetch_gupy(client, f"{origin}/jobs/{identifier}"))
    return records
