"""Bloqueia segredos e documentos pessoais no índice Git, sem imprimir valores."""
import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", action="store_true", help="Inclui arquivos novos não ignorados na revisão local")
    args = parser.parse_args()
    git = shutil.which("git")
    if not git:
        raise SystemExit("Git não encontrado.")
    command = [git, "ls-files", "-z"]
    if args.worktree:
        command.extend(["--cached", "--others", "--exclude-standard"])
    names = sorted(set(subprocess.check_output(command, cwd=ROOT).decode().split("\0")))
    secrets = []
    local_env = ROOT / ".env"
    if local_env.exists():
        from dotenv import dotenv_values
        secrets = [str(value).encode() for key, value in dotenv_values(local_env).items()
                   if value and len(str(value)) >= 16
                   and any(word in key.upper() for word in ("KEY", "TOKEN", "PASSWORD"))]
    pattern = re.compile(rb"(?:gsk_[A-Za-z0-9]{24,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)")
    problems = []
    for name in filter(None, names):
        path = Path(name)
        if ((path.name.startswith(".env") and path.name != ".env.example")
                or path.suffix.lower() in {".pdf", ".docx", ".db", ".sqlite", ".sqlite3", ".dump", ".sql"}
                or any(part in {".venv", "node_modules", ".next", ".runtime", "audit-artifacts"} for part in path.parts)):
            problems.append(name)
            continue
        if args.worktree:
            working_path = ROOT / path
            if not working_path.is_file():
                continue
            content = working_path.read_bytes()
        else:
            content = subprocess.check_output([git, "show", f":{name}"], cwd=ROOT)
        if pattern.search(content) or any(secret in content for secret in secrets):
            problems.append(name)
    if problems:
        print("Publicação bloqueada. Revise os arquivos indicados (valores omitidos):")
        for name in problems:
            print(name)
        raise SystemExit(1)
    print(f"Verificação aprovada: {len(list(filter(None, names)))} arquivos, sem segredos detectados nem documentos pessoais incluídos.")


if __name__ == "__main__":
    main()
