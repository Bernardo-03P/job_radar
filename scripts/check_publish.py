"""Bloqueia segredos e documentos pessoais no índice Git, sem imprimir valores."""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    git = shutil.which("git")
    if not git:
        raise SystemExit("Git não encontrado.")
    names = subprocess.check_output([git, "ls-files", "-z"], cwd=ROOT).decode().split("\0")
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
                or any(part in {".venv", "node_modules", ".next", "audit-artifacts"} for part in path.parts)):
            problems.append(name)
            continue
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
