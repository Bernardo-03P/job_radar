"""Serviços sob demanda; cinco minutos de inatividade após solicitações formais."""
import argparse
import os
import subprocess
import sys
import time
from contextlib import contextmanager

from dotenv import dotenv_values

from . import runtime
from .collect_jobs import write_json
from .daily_run import exclusive_run, read_state
from .formal_activity import snapshot
from .local_api import local_api_url
from .search_session import ROOT, RUNTIME, container_running, stop_backend

IDLE_SECONDS = 300


@contextmanager
def service_lock(timeout=240, lock_root=None):
    lock_root = lock_root or RUNTIME
    deadline = time.monotonic() + timeout
    while True:
        with exclusive_run(lock_root / 'service-use.lock') as acquired:
            if acquired:
                yield
                return
        if time.monotonic() >= deadline:
            raise ValueError('Os serviços estão ocupados. Aguarde a solicitação atual terminar.')
        time.sleep(0.5)


def expired(state, now, activity=None):
    activity = activity or {}
    if any(expiry > now for expiry in activity.get('active', {}).values()):
        return False
    last = max(state['last_request_finished'], activity.get('last_finished', 0))
    return now - last >= IDLE_SECONDS


def ensure_worker(config):
    deadline = time.monotonic() + 240
    last_spawn = -10
    while time.monotonic() < deadline:
        with exclusive_run(RUNTIME / 'interactive-worker.lock') as available:
            if available and time.monotonic() - last_spawn >= 2:
                if os.name == 'nt':
                    shell = os.path.join(os.environ.get('SystemRoot', 'C:/Windows'), 'System32/WindowsPowerShell/v1.0/powershell.exe')
                    runtime.checked([shell, '-NoProfile', '-NonInteractive', '-Command',
                                     "Start-ScheduledTask -TaskName 'JobRadar-Interactive-Session'"], timeout=30)
                else:
                    runtime.spawn([sys.executable, '-m', 'agent.interactive_session', '--worker'], 'interactive-session.log')
                last_spawn = time.monotonic()
        state = read_state(RUNTIME / 'interactive-session.json')
        if not available and state.get('status') == 'ready' and runtime.backend_ready(local_api_url(config.get('JOB_RADAR_API_URL'))):
            return
        time.sleep(1)
    raise ValueError('A inicialização do Job Radar não foi confirmada. Confira o diagnóstico local.')


@contextmanager
def request_context(config):
    # A autorização do chat é verificada pelo bridge antes de chegar aqui.
    for _ in range(2):
        ensure_worker(config)
        with service_lock():
            state = read_state(RUNTIME / 'interactive-session.json')
            if state.get('status') != 'ready':
                continue
            try:
                yield
            finally:
                state['last_request_finished'] = time.time()
                write_json(RUNTIME / 'interactive-session.json', state)
            return
    raise ValueError('A sessão encerrou durante a conexão; tente novamente.')


def worker(config):
    with exclusive_run(RUNTIME / 'interactive-worker.lock') as acquired:
        if not acquired:
            return
        pids = []
        docker = runtime.executable('docker')
        database_owned = False
        state = {'status': 'starting', 'idle_seconds': IDLE_SECONDS, 'last_request_finished': time.time()}
        errors = []
        try:
            with service_lock():
                write_json(RUNTIME / 'interactive-session.json', state)
                database_owned = not container_running(docker)
                runtime.ensure_backend(config, on_start=pids.append)
                if runtime.ensure_frontend(on_start=pids.append) != 'ready':
                    raise ValueError('O site não possui build disponível.')
                state.update({'status': 'ready', 'last_request_finished': time.time()})
                state.update({'worker_pid': os.getpid(), 'owned_pids': list(pids), 'database_owned': database_owned})
                write_json(RUNTIME / 'interactive-session.json', state)
            while True:
                time.sleep(1)
                with exclusive_run(RUNTIME / 'service-use.lock') as idle:
                    if not idle:
                        continue  # Nunca interrompe uma solicitação em andamento.
                    state = read_state(RUNTIME / 'interactive-session.json')
                    if not expired(state, time.time(), snapshot(RUNTIME)):
                        continue
                    state['status'] = 'closing'
                    write_json(RUNTIME / 'interactive-session.json', state)
                    break
        finally:
            with service_lock():
                for pid in reversed(pids):
                    try:
                        stop_backend(pid)
                    except (OSError, ValueError, subprocess.SubprocessError):
                        errors.append('process')
                if database_owned:
                    try:
                        runtime.checked([docker, 'stop', 'job_radar_postgres'], timeout=30)
                    except (OSError, ValueError, subprocess.SubprocessError):
                        errors.append('database')
                state.update({'status': 'cleanup_failed' if errors else 'closed', 'cleanup_errors': errors})
                write_json(RUNTIME / 'interactive-session.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', required=True)
    parser.parse_args()
    worker(dotenv_values(ROOT / '.env'))


if __name__ == '__main__':
    main()
