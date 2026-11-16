"""Sinalização sem conteúdo pessoal de gerações iniciadas pelo site."""
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .collect_jobs import write_json
from .daily_run import exclusive_run, read_state

RUNTIME = Path(__file__).resolve().parents[1] / '.runtime'


def snapshot(root=None):
    root = root or RUNTIME
    return read_state(root / 'formal-activity.json')


def change(identifier, active):
    with exclusive_run(RUNTIME / 'formal-activity.lock') as acquired:
        if not acquired:
            raise ValueError('Registro de atividade ocupado; tente novamente.')
        now = time.time()
        state = snapshot()
        requests = {key: expiry for key, expiry in state.get('active', {}).items() if expiry > now}
        if active:
            requests[identifier] = now + 900
        else:
            requests.pop(identifier, None)
            state['last_finished'] = now
        state['active'] = requests
        write_json(RUNTIME / 'formal-activity.json', state)


@contextmanager
def formal_activity():
    if read_state(RUNTIME / 'interactive-session.json').get('status') != 'ready':
        yield
        return
    identifier = uuid4().hex
    change(identifier, True)
    try:
        yield
    finally:
        change(identifier, False)
