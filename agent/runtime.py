"""Inicializa os serviços locais e recupera a busca atrasada no Hermes existente."""
import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

from .collect_jobs import write_json
from .daily_run import RUNTIME, exclusive_run, read_state, run_once, scheduled_slot
from .local_api import local_api_url

ROOT = Path(__file__).resolve().parents[1]


def executable(name, home=None):
    program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    known = {
        "hermes": (Path(home) if home else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "hermes") / "bin/hermes.exe",
        "docker": program_files / "Docker/Docker/resources/bin/docker.exe",
        "node": program_files / "nodejs/node.exe",
    }
    candidate = known.get(name)
    found = str(candidate) if candidate and candidate.is_file() else shutil.which(name)
    if not found:
        raise ValueError(f"Executável necessário não encontrado: {name}")
    path = Path(found).resolve()
    if ROOT in path.parents:
        raise ValueError("O executável externo não pode vir da pasta do projeto.")
    return str(path)


def checked(arguments, timeout=60, cwd=None, env=None):
    result = subprocess.run(arguments, cwd=cwd or ROOT, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x08000000 if os.name == "nt" else 0,
                            check=False, timeout=timeout, env=env)
    if result.returncode:
        raise ValueError("Um serviço local não confirmou a operação; confira o diagnóstico.")


def spawn(arguments, log_name, detached=True):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log = RUNTIME / log_name
    if log.exists() and log.stat().st_size > 2 * 1024 * 1024:
        log.replace(log.with_suffix(".log.1"))
    options = {"creationflags": 0x08000000 | (0x00000008 if detached else 0)} if os.name == "nt" else {"start_new_session": True}
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        options["startupinfo"] = startup
    with log.open("ab") as output:
        process = subprocess.Popen(arguments, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=output, **options)
    return process.pid


def backend_ready(base):
    try:
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            response = client.get(base + "/health")
            return response.is_success and response.json() == {"status": "ok"}
    except (httpx.HTTPError, ValueError):
        return False


def ensure_backend(config, on_start=None):
    base = local_api_url(config.get("JOB_RADAR_API_URL"))
    if backend_ready(base):
        return
    parsed = urlsplit(base)
    if parsed.scheme != "http":
        raise ValueError("A inicialização automática suporta HTTP local; inicie o serviço HTTPS manualmente.")
    docker = executable("docker")
    try:
        checked([docker, "info"], timeout=10)
    except (ValueError, subprocess.TimeoutExpired):
        desktop = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Docker/Docker/Docker Desktop.exe"
        if not desktop.is_file():
            raise ValueError("Docker Desktop não encontrado.") from None
        spawn([str(desktop)], "docker-start.log")
        ready = False
        for _ in range(60):
            time.sleep(2)
            try:
                checked([docker, "info"], timeout=5)
                ready = True
                break
            except (ValueError, subprocess.TimeoutExpired):
                continue
        if not ready:
            raise ValueError("Docker não ficou disponível; a tarefa tentará novamente.")
    checked([docker, "compose", "up", "-d", "--wait"], timeout=120)
    pid = spawn([sys.executable, "-m", "uvicorn", "main:app", "--app-dir", str(ROOT / "backend"),
                 "--host", parsed.hostname, "--port", str(parsed.port or 80)], "backend.log",
                detached=on_start is None)
    if on_start:
        on_start(pid)
    for _ in range(30):
        if backend_ready(base):
            return
        time.sleep(2)
    raise ValueError("O backend não ficou disponível; a tarefa tentará novamente.")


def ensure_frontend():
    frontend = ROOT / "frontend"
    if not (frontend / ".next/BUILD_ID").is_file():
        return "not_built"

    def ready():
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                response = client.get("http://127.0.0.1:3000")
                return response.is_success and "tech job radar" in response.text.lower()
        except httpx.HTTPError:
            return False

    if ready():
        return "ready"
    node = executable("node")
    spawn([node, str(frontend / "node_modules/next/dist/bin/next"), "start", str(frontend),
           "--hostname", "127.0.0.1", "--port", "3000"], "frontend.log")
    for _ in range(20):
        if ready():
            return "ready"
        time.sleep(1)
    raise ValueError("O frontend não ficou disponível.")


def queue_due(config, hermes, now):
    state = read_state(RUNTIME / "daily-state.json")
    slot = scheduled_slot(now)
    if state.get("completed_slot", "") >= slot:
        return "already_completed"
    installation = read_state(RUNTIME / "automation-install.json")
    job_id = installation.get("hermes_job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("Agendamento do projeto não foi instalado.")
    queued = read_state(RUNTIME / "runtime-queue.json")
    if queued.get("slot") == slot and queued.get("queued_at"):
        if queued.get("attempts", 0) >= 3:
            return "retry_limit_reached"
        previous = datetime.fromisoformat(queued["queued_at"])
        if now - previous < timedelta(hours=1):
            return "recently_queued"
    environment = os.environ.copy()
    environment["HERMES_HOME"] = str(config["JOB_RADAR_HERMES_HOME"])
    record = {"slot": slot, "queued_at": now.isoformat(), "status": "running",
              "attempts": queued.get("attempts", 0) + 1 if queued.get("slot") == slot else 1}
    write_json(RUNTIME / "runtime-queue.json", record)
    try:
        # Nesta instalação o CLI executa o job sincronamente, inclusive a busca web.
        checked([hermes, "cron", "run", job_id], timeout=900, env=environment)
        record["status"] = "completed"
    except (ValueError, OSError, subprocess.SubprocessError):
        record["status"] = "unconfirmed"
        try:
            fallback = run_once(config, now=now)
            if fallback.get("status") in {"completed", "partial", "already_completed"}:
                record["status"] = "fallback_completed"
        except (ValueError, OSError, KeyError, TypeError, httpx.HTTPError):
            pass
    write_json(RUNTIME / "runtime-queue.json", record)
    if record["status"] == "fallback_completed":
        return "fallback_completed"
    return "queued" if record["status"] == "completed" else "unconfirmed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensure", action="store_true", required=True)
    parser.add_argument("--queue-due", action="store_true")
    parser.add_argument("--watch", action="store_true", help="Mantém o supervisor da tarefa Windows ativo")
    args = parser.parse_args()
    while True:
        result = {"checked_at": datetime.now(timezone.utc).isoformat()}
        try:
            with exclusive_run(RUNTIME / "runtime.lock") as acquired:
                if not acquired:
                    return
                config = dotenv_values(ROOT / ".env")
                home = Path(str(config.get("JOB_RADAR_HERMES_HOME") or ""))
                if not (home / "config.yaml").is_file():
                    raise ValueError("Configure a instalação existente do Hermes.")
                result["step"] = "backend"
                ensure_backend(config)
                result["step"] = "frontend"
                result["frontend"] = ensure_frontend()
                result["step"] = "gateway"
                hermes = executable("hermes", home=home)
                environment = os.environ.copy()
                environment["HERMES_HOME"] = str(home.resolve())
                checked([hermes, "gateway", "ensure"], timeout=90, env=environment)
                result["status"] = "ready"
                if args.queue_due:
                    result["step"] = "recovery"
                    result["recovery"] = queue_due(config, hermes, datetime.now(timezone.utc))
                result["step"] = "ready"
                write_json(RUNTIME / "runtime-status.json", result)
        except (ValueError, OSError, subprocess.SubprocessError, httpx.HTTPError):
            result["status"] = "unavailable"
            write_json(RUNTIME / "runtime-status.json", result)
            if not args.watch:
                parser.exit(1, "Serviços ainda indisponíveis. Confira .runtime/runtime-status.json.\n")
        if not args.watch:
            return
        time.sleep(900)


if __name__ == "__main__":
    main()
