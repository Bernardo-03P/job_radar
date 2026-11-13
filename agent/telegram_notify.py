"""Avisos agendados somente ao dono fixo do bot existente; sem geração de currículo."""
import json
import re
from pathlib import Path

import httpx
from dotenv import dotenv_values


def send_notification(config, message):
    owner = str(config.get("JOB_RADAR_TELEGRAM_OWNER_ID") or "")
    if not owner.isdigit() or int(owner) <= 0:
        raise ValueError("Proprietário privado do Telegram não configurado.")
    home = Path(str(config.get("JOB_RADAR_HERMES_HOME") or ""))
    if not (home / "config.yaml").is_file():
        raise ValueError("Instalação existente do Hermes não encontrada.")
    values = dotenv_values(home / ".env")
    raw_allowed = str(values.get("TELEGRAM_ALLOWED_USERS") or "")
    try:
        parsed = json.loads(raw_allowed)
    except ValueError:
        parsed = None
    allowed = [str(item) for item in parsed] if isinstance(parsed, list) else re.split(r"[,\s]+", raw_allowed.strip())
    if owner not in allowed or any(not item.isdigit() or int(item) <= 0 for item in allowed):
        raise ValueError("O dono do Radar precisa estar autorizado explicitamente no bot existente.")
    token = values.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Token do bot existente não configurado.")
    try:
        with httpx.Client(timeout=30, follow_redirects=False,
                          proxy=values.get("TELEGRAM_PROXY") or None) as client:
            response = client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                   json={"chat_id": owner, "text": message[:3900],
                                         "link_preview_options": {"is_disabled": True}})
        result = response.json()
        if not response.is_success or not isinstance(result, dict) or result.get("ok") is not True:
            raise ValueError("O Telegram não confirmou o aviso.")
    except (httpx.HTTPError, ValueError):
        raise ValueError("Aviso não confirmado pelo Telegram; confira o estado antes de reenviar.") from None
    return {"status": "sent", "message_id": result.get("result", {}).get("message_id")}
