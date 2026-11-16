import shutil
import subprocess
import sys
from pathlib import Path

from agent.job_profile import load_profile, schedule_group
from agent.mock_crawler import DEMO_JOBS

ROOT = Path(__file__).resolve().parents[2]


def test_public_demo_populates_both_schedule_groups():
    assert [schedule_group(job, load_profile()) for job in DEMO_JOBS] == ['confirmed', 'unconfirmed']


def test_direct_demo_entrypoint_can_show_help_without_services():
    result = subprocess.run([sys.executable, 'agent/mock_crawler.py', '--help'], cwd=ROOT,
                            capture_output=True, timeout=20)
    assert result.returncode == 0
    assert b'--demo' in result.stdout


def test_history_scan_finds_deleted_secret_and_does_not_print_it(tmp_path):
    git = shutil.which('git')
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy2(ROOT / 'scripts/check_publish.py', scripts / 'check_publish.py')

    def command(*args):
        return subprocess.run([git, *args], cwd=tmp_path, capture_output=True, check=True)

    command('init', '--quiet')
    secret = 'gsk_' + 'a' * 40
    file = tmp_path / 'secret.txt'
    file.write_text(secret)
    command('add', 'secret.txt')
    command('-c', 'user.name=Audit Test', '-c', 'user.email=audit@example.invalid', 'commit', '-qm', 'synthetic fixture')
    file.unlink()
    (tmp_path / 'README.md').write_text('Example')
    command('add', '-A')
    command('-c', 'user.name=Audit Test', '-c', 'user.email=audit@example.invalid', 'commit', '-qm', 'remove synthetic fixture')
    clean = subprocess.run([sys.executable, 'scripts/check_publish.py'], cwd=tmp_path, capture_output=True, timeout=20)
    history = subprocess.run([sys.executable, 'scripts/check_publish.py', '--history'], cwd=tmp_path,
                             capture_output=True, timeout=20)
    assert clean.returncode == 0
    assert history.returncode == 1
    assert b'secret.txt' in history.stdout
    assert secret.encode() not in history.stdout + history.stderr
