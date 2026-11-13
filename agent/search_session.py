"""Liga API/banco só durante a busca; encerra recursos próprios em sucesso ou falha."""
import argparse
import csv
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

from . import daily_run, runtime
from .collect_jobs import write_json
from .local_api import local_api_url

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def container_running(docker):
    result = subprocess.run([docker, "inspect", "--format", "{{.State.Running}}", "job_radar_postgres"],
                            capture_output=True, text=True, timeout=15,
                            creationflags=0x08000000 if os.name == "nt" else 0)
    if result.returncode:
        return False
    return result.stdout.strip() == "true"


def stop_backend(pid):
    if os.name == "nt":
        system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
        def running():
            result = subprocess.run([str(system_root / "System32/tasklist.exe"), "/FI", f"PID eq {pid}",
                                     "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=15,
                                    creationflags=0x08000000)
            result.check_returncode()
            return any(len(row) > 1 and row[1] == str(pid) for row in csv.reader(result.stdout.splitlines()))
        if not running():
            return
        try:
            runtime.checked([str(system_root / "System32/taskkill.exe"), "/PID", str(pid), "/T", "/F"], timeout=20)
        except ValueError:
            if running():
                raise
    else:
        import signal
        os.killpg(pid, signal.SIGTERM)


def run_session(config, force=False, input_path=None, notify=True, now=None):
    now = now or datetime.now(timezone.utc)
    with daily_run.exclusive_run(RUNTIME / "search-session.lock") as acquired:
        if not acquired:
            return {"status": "busy"}
        slot = daily_run.scheduled_slot(now)
        state = daily_run.read_state(RUNTIME / "daily-state.json")
        if not force and state.get("completed_slot", "") >= slot:
            return {"status": "already_completed", "slot": slot, "services_started": False}
        base = local_api_url(config.get("JOB_RADAR_API_URL"))
        docker = runtime.executable("docker")
        db_was_running = container_running(docker)
        api_was_running = runtime.backend_ready(base)
        backend_pids = []
        status = {"started_at": now.isoformat(), "status": "starting",
                  "backend_started": False, "database_was_running": db_was_running,
                  "frontend_started": False}
        cleanup_errors = []
        try:
            write_json(RUNTIME / "search-session.json", status)
            if not api_was_running:
                runtime.ensure_backend(config, on_start=backend_pids.append)
            status["backend_started"] = bool(backend_pids)
            status["status"] = "searching"
            write_json(RUNTIME / "search-session.json", status)
            return daily_run.run_once(config, now=now, force=force, input_path=input_path, notify=notify)
        finally:
            for pid in reversed(backend_pids):
                try:
                    stop_backend(pid)
                except (OSError, ValueError, subprocess.SubprocessError):
                    cleanup_errors.append("backend")
            if not db_was_running and not api_was_running:
                try:
                    runtime.checked([docker, "stop", "job_radar_postgres"], timeout=30)
                except (OSError, ValueError, subprocess.SubprocessError):
                    cleanup_errors.append("database")
            status.update({"finished_at": datetime.now(timezone.utc).isoformat(),
                           "backend_started": bool(backend_pids),
                           "status": "cleanup_failed" if cleanup_errors else "closed",
                           "cleanup_errors": cleanup_errors})
            write_json(RUNTIME / "search-session.json", status)
            if cleanup_errors:
                raise ValueError("Falha no desligamento; confira search-session.json.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scheduled", action="store_true")
    mode.add_argument("--run-now", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()
    try:
        if args.input:
            path = args.input.resolve()
            if RUNTIME.resolve() not in path.parents or path.suffix != ".json":
                raise ValueError("A descoberta deve ficar em .runtime.")
        result = run_session(dotenv_values(ROOT / ".env"), force=args.run_now,
                             input_path=args.input, notify=not args.no_notify)
        print(json.dumps(result, ensure_ascii=True))
    except (ValueError, OSError, subprocess.SubprocessError, httpx.HTTPError):
        parser.exit(1, "A sessão de busca falhou; confira o relatório local de desligamento.\n")


if __name__ == "__main__":
    main()
