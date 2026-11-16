"""Consulta o Job Radar pelo Hermes; envio de Markdown só ao proprietário em DM."""
import argparse
import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from uuid import UUID

import httpx
from dotenv import dotenv_values

if __package__:
    from .local_api import local_api_url
else:
    from local_api import local_api_url

ROOT = Path(__file__).resolve().parents[1]


def require_private_context(config, environment=None, local=False):
    environment = os.environ if environment is None else environment
    owner = str(config.get("JOB_RADAR_TELEGRAM_OWNER_ID") or "")
    if not owner.isdigit() or int(owner) <= 0:
        raise PermissionError("O proprietário privado do Telegram não foi configurado.")
    platform = environment.get("HERMES_SESSION_PLATFORM", "")
    context_keys = ("HERMES_SESSION_PLATFORM", "HERMES_SESSION_ID", "HERMES_SESSION_KEY",
                    "HERMES_SESSION_CHAT_ID", "HERMES_SESSION_CHAT_TYPE",
                    "HERMES_SESSION_USER_ID", "HERMES_SESSION_ACTOR_ID")
    if local and not any(environment.get(key) for key in context_keys):
        return
    actor = environment.get("HERMES_SESSION_ACTOR_ID") or environment.get("HERMES_SESSION_USER_ID")
    if not (platform == "telegram" and environment.get("HERMES_SESSION_CHAT_TYPE") == "dm"
            and environment.get("HERMES_SESSION_CHAT_ID") == owner and actor == owner):
        raise PermissionError("Currículos disponíveis somente no chat privado do proprietário autorizado.")


def api_request(config, method, path, params=None, payload=None):
    base = local_api_url(config.get("JOB_RADAR_API_URL"))
    key = config.get("RESUME_API_KEY")
    if not key:
        raise ValueError("Configure a chave privada RESUME_API_KEY do projeto.")
    with httpx.Client(timeout=180, follow_redirects=False, trust_env=False) as client:
        response = client.request(method, base + path, params=params, json=payload,
                                  headers={"X-API-Key": key})
    if not response.is_success:
        raise ValueError(f"Job Radar retornou HTTP {response.status_code}. Confira o serviço local e a versão solicitada.")
    return {"deleted": True} if response.status_code == 204 else response.json()


def send_document(config, version):
    """O destino vem da configuração local; o modelo não escolhe outro chat."""
    require_private_context(config)
    home = Path(str(config.get("JOB_RADAR_HERMES_HOME") or ""))
    values = dotenv_values(home / ".env")
    token = values.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Token do bot não encontrado na instalação existente do Hermes.")
    document = BytesIO(version["data"]["adapted_resume_markdown"].encode("utf-8"))
    try:
        with httpx.Client(timeout=30, follow_redirects=False,
                          proxy=values.get("TELEGRAM_PROXY") or None) as client:
            response = client.post(f"https://api.telegram.org/bot{token}/sendDocument",
                                   data={"chat_id": config["JOB_RADAR_TELEGRAM_OWNER_ID"],
                                         "caption": f"Currículo adaptado — {version['job_title'][:150]}"},
                                   files={"document": (f"curriculo-{version['id']}.md", document,
                                                       "text/markdown")})
        try:
            result = response.json()
        except ValueError:
            result = None
        if not response.is_success or not isinstance(result, dict) or not result.get("ok"):
            raise ValueError("O Telegram não confirmou o envio. Confira o bot e o chat privado.")
    except httpx.HTTPError:
        raise ValueError("Falha de comunicação com o Telegram. Nenhuma credencial foi exibida.") from None
    finally:
        document.close()
    return {"status": "sent", "version_id": version["id"]}


def summary(version):
    return {key: version[key] for key in ("id", "job_id", "job_title", "company", "created_at")} | {
        "match_score": version["data"]["match_score"],
        "metric_description": "Porcentagem de palavras-chave presentes; não prevê contratação nem aprovação ATS.",
    }


def generate_selected(config, job_id, source_id, confirmed=False):
    require_private_context(config)
    if not confirmed or type(job_id) is not int or job_id <= 0:
        raise ValueError("Escolha uma vaga e confirme a geração antes de chamar a IA.")
    try:
        source_id = str(UUID(str(source_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Escolha um PDF guardado válido pelo site.") from None
    response = api_request(config, "POST", "/api/v1/resumes/tailor-saved",
                           payload={"job_id": job_id, "source_id": source_id})
    return {**summary(response["version"]), "cached": response.get("cached", False),
            "status": "ready", "sent": False}


def search_now(config, include_discovery=False):
    require_private_context(config)
    arguments = [sys.executable, "-m", "agent.search_session", "--run-now", "--no-notify"]
    if include_discovery:
        arguments.extend(["--input", str(ROOT / ".runtime/telegram-candidates.json")])
    try:
        response = subprocess.run(arguments, cwd=ROOT, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", timeout=900, check=False,
                                  creationflags=0x08000000 if os.name == "nt" else 0)
        if response.returncode:
            raise ValueError()
        result = json.loads(response.stdout)
        if not isinstance(result, dict) or result.get("status") not in {
                "completed", "partial", "busy", "already_completed"}:
            raise ValueError()
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError("A busca manual não foi confirmada. Consulte as vagas e o status antes de repetir.") from None
    return {**result, "reply_in_current_chat": True, "automatic_notification": False}


def execute_command(args, config):
    if args.command == "status":
        result = {"backend": api_request(config, "GET", "/health"),
                  "versoes_listadas": len(api_request(config, "GET", "/api/v1/resumes/versions"))}
    elif args.command == "vagas":
        result = api_request(config, "GET", "/api/v1/jobs",
                             {"q": args.query, "limit": 20, "matching_profile": "true", "include_unconfirmed_hours": "true"})
        result = [{key: item[key] for key in ("id", "title", "company", "location", "skills", "source_url", "schedule_status")}
                  for item in result]
    elif args.command == "curriculos":
        result = [summary(item) for item in api_request(config, "GET", "/api/v1/resumes/versions",
                                                       {"q": args.query, "limit": 20})]
    elif args.command == "fontes":
        result = api_request(config, "GET", "/api/v1/resumes/sources")
    elif args.command == "gerar":
        result = generate_selected(config, args.job_id, args.source_id, args.confirmar)
    elif args.command == "buscar":
        result = search_now(config, args.incluir_descoberta)
    else:
        if not args.version_id:
            raise ValueError("Informe o ID completo de uma versão salva.")
        path = f"/api/v1/resumes/versions/{args.version_id}"
        if args.command == "excluir":
            result = api_request(config, "DELETE", path)
        else:
            version = api_request(config, "GET", path)
            result = send_document(config, version) if args.command == "enviar" else {
                **summary(version), "adapted_resume_markdown": version["data"]["adapted_resume_markdown"],
                "missing_critical_skills": version["data"]["missing_critical_skills"],
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="Diagnóstico pelo terminal local, fora de sessões Hermes")
    parser.add_argument("command", choices=["status", "vagas", "buscar", "fontes", "gerar", "curriculos", "curriculo", "enviar", "excluir"])
    parser.add_argument("version_id", nargs="?", type=lambda value: str(UUID(value)))
    parser.add_argument("--query", default="")
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--source-id", type=lambda value: str(UUID(value)))
    parser.add_argument("--confirmar", action="store_true")
    parser.add_argument("--incluir-descoberta", action="store_true")
    args = parser.parse_args()
    config = dotenv_values(ROOT / ".env")
    try:
        require_private_context(config, local=args.local)
        if args.command == "gerar" and (not args.confirmar or not args.source_id or not args.job_id or args.job_id <= 0):
            raise ValueError("Escolha uma vaga e um PDF guardado e confirme a geração.")
        if args.command == "buscar":
            result = execute_command(args, config)
        else:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from agent.interactive_session import request_context
            with request_context(config):
                result = execute_command(args, config)
        print(json.dumps(result, ensure_ascii=True))
    except (PermissionError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    except httpx.HTTPError:
        parser.exit(1, "Não foi possível conectar ao backend local. Inicie o Job Radar.\n")


if __name__ == "__main__":
    main()
