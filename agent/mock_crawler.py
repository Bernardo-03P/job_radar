"""Ingestão de fixtures/JSON e registro explícito do job Hermes; sem IA neste script."""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv

if __package__:
    from .local_api import local_api_url
else:
    from local_api import local_api_url

ROOT = Path(__file__).resolve().parents[1]
DEMO_JOBS = [
    {"title": "Backend Python · demonstração", "company": "Empresa Exemplo (fictícia)",
     "location": "Remoto · Brasil", "description": (
         "Vaga fictícia para demonstração. Desenvolvimento de APIs com Python e FastAPI, "
         "persistência em PostgreSQL, testes com pytest e serviços com Docker."
     ), "source_url": "https://example.com/demo/backend-python",
     "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"]},
    {"title": "Engenharia de Dados · demonstração", "company": "Laboratório Exemplo (fictício)",
     "location": "Remoto", "description": (
         "Vaga fictícia para demonstração. Construção de pipelines em Python e SQL, "
         "modelagem de dados, automação de testes e uso de PostgreSQL."
     ), "source_url": "https://example.com/demo/data-engineer",
     "skills": ["Python", "SQL", "PostgreSQL"]},
]


def register_hermes(config):
    values = dotenv_values(ROOT / ".env")
    home = Path(os.environ.get("HERMES_HOME") or values.get("JOB_RADAR_HERMES_HOME")
                or (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "hermes"
                    if os.name == "nt" else Path.home() / ".hermes")).resolve()
    if not (home / "config.yaml").is_file():
        raise ValueError("Configure a instalação existente em JOB_RADAR_HERMES_HOME.")
    jobs_file = home / "cron/jobs.json"
    if jobs_file.is_file():
        payload = json.loads(jobs_file.read_text(encoding="utf-8"))
        jobs = payload if isinstance(payload, list) else payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise ValueError("Não foi possível verificar os cron jobs existentes; nenhum job foi criado.")
        matching = [item for item in jobs if isinstance(item, dict) and item.get("name") == config["name"]]
        if matching:
            print("Job do Radar já cadastrado; nenhum agendamento duplicado foi criado.")
            return
    executable = shutil.which("hermes")
    if not executable:
        raise ValueError("Hermes não encontrado no PATH.")
    executable = str(Path(executable).resolve())
    if ROOT in Path(executable).parents:
        raise ValueError("O executável do Hermes deve pertencer à instalação externa ao projeto.")
    if not isinstance(config.get("schedule"), str) or not 1 <= len(config["schedule"]) <= 100:
        raise ValueError("Agendamento inválido.")
    subprocess.run([
        executable, "cron", "create", config["schedule"], config["prompt"],
        "--name", config["name"], "--timezone", config["timezone"], "--workdir", str(ROOT),
        "--deliver", "local", "--catch-up", "off",
    ], check=True, shell=False, timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Insere vagas explicitamente fictícias")
    group.add_argument("--input", type=Path, help="Lista JSON extraída de fontes públicas")
    group.add_argument("--register-hermes", action="store_true", help="Registra o cron no Hermes")
    args = parser.parse_args()
    if args.register_hermes:
        config = json.loads((ROOT / "agent/hermes_cron.json").read_text(encoding="utf-8"))
        register_hermes(config)
        return
    load_dotenv(ROOT / ".env")
    key = os.getenv("INGEST_API_KEY")
    if not key:
        parser.error("Configure INGEST_API_KEY no .env antes da ingestão.")
    if args.input:
        source = args.input.resolve()
        if ROOT not in source.parents or source.suffix.lower() != ".json":
            parser.error("Use um arquivo JSON de vagas dentro da pasta do projeto.")
    jobs = DEMO_JOBS if args.demo else json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(jobs, list):
        parser.error("O arquivo precisa conter uma lista de vagas.")
    endpoint = local_api_url(os.getenv("JOB_RADAR_API_URL"))
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        for job in jobs:
            response = client.post(endpoint + "/api/v1/jobs", json=job, headers={"X-API-Key": key})
            response.raise_for_status()
            print(f"Vaga recebida: {response.json()['id']}")


if __name__ == "__main__":
    main()
