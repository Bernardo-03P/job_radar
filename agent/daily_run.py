"""Coleta/ingestão diária idempotente; nunca gera currículos automaticamente."""
import argparse
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import dotenv_values

from backend.app.schemas.job import JobCreate, canonical_source_url

from .collect_jobs import collect, write_json
from .job_profile import load_profile, prioritize, profile_match
from .local_api import local_api_url
from .telegram_notify import send_notification

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
ZONE = ZoneInfo("America/Sao_Paulo")


@contextmanager
def exclusive_run(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
        try:
            yield acquired
        finally:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def scheduled_slot(now):
    local = now.astimezone(ZONE)
    date = local.date() if local.hour >= 9 else local.date() - timedelta(days=1)
    while date.weekday() > 4:
        date -= timedelta(days=1)
    return date.isoformat()


def read_state(path):
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise ValueError("Estado da automação inválido; revise antes de repetir os avisos.") from None


def discovery_jobs(path, now, profile):
    if path is None or not path.is_file():
        return [], {"status": "not_supplied", "selected": 0}
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Lote de descoberta excede o limite.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    timestamp = datetime.fromisoformat(payload["checked_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or not timedelta(0) <= now - timestamp <= timedelta(hours=8):
        raise ValueError("Lote de descoberta antigo ou com horário inválido.")
    values = payload["jobs"]
    if not isinstance(values, list) or len(values) > 200:
        raise ValueError("Lista de descoberta inválida.")
    jobs, rejected, review = [], 0, []
    for item in values:
        job = JobCreate.model_validate(item).model_dump(mode="json")
        matched, reason = profile_match(job, profile)
        if matched:
            jobs.append(job)
        else:
            rejected += 1
            review.append({"reason": reason, "job": job})
    return jobs, {"status": "supplied", "selected": len(jobs), "filtered": rejected, "review": review}


def list_existing(client, endpoint):
    existing, offset = {}, 0
    while True:
        response = client.get(endpoint + "/api/v1/jobs", params={"limit": 100, "offset": offset})
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("A API local retornou uma lista inválida.")
        existing.update({canonical_source_url(job["source_url"]): job["id"] for job in page})
        if len(page) < 100:
            return existing
        offset += 100
        if offset > 100000:
            raise ValueError("Paginação excedeu o limite seguro.")


def digest(report):
    text = [f"Job Radar — busca de {report['slot']}",
            f"{report['selected']} vagas compatíveis nesta rodada; {len(report['new_jobs'])} novas.",
            "Estágio prioritário · Dados/IA, Sistemas e Suporte."]
    if report.get("shortfall", 0):
        text.append(f"Meta: {report['minimum_results']} vagas. Faltam {report['shortfall']} validadas; "
                    "os filtros foram preservados.")
    for job in report["new_jobs"][:5]:
        text.extend([f"\n#{job['id']} {job['title'][:150]} — {job['company'][:70]}", job["source_url"]])
    if report["failed_sources"]:
        text.append("\nBusca parcial: houve fontes indisponíveis. Confira o relatório local.")
    if report["discovery"]["status"] == "not_supplied":
        text.append("\nEsta rodada consultou as fontes automáticas; a descoberta complementar não foi fornecida.")
    text.append("\nPara gerar um currículo, escolha a vaga no chat privado. Nenhum currículo foi gerado nesta busca.")
    return "\n".join(text)[:3900]


def run_once(config, now=None, force=False, input_path=None, notify=True):
    now = now or datetime.now(timezone.utc)
    slot = scheduled_slot(now)
    state_path = RUNTIME / "daily-state.json"
    with exclusive_run(RUNTIME / "daily.lock") as acquired:
        if not acquired:
            return {"status": "busy", "slot": slot}
        state = read_state(state_path)
        if not force and state.get("completed_slot", "") >= slot:
            return {"status": "already_completed", "slot": slot}
        profile = load_profile()
        target = profile.get("minimum_results", 10)
        if type(target) is not int or not 1 <= target <= 50:
            raise ValueError("A meta precisa estar entre 1 e 50 vagas.")
        sources = json.loads((ROOT / "agent/job_sources.json").read_text(encoding="utf-8"))
        jobs, reports, failures, review = [], [], [], []
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
            for source in sources:
                try:
                    found, report = collect(client, [source], limit=100, profile=profile)
                    jobs.extend(found)
                    reports.extend(report["sources"])
                    review.extend(report["review"])
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    failures.append(source.get("board") or source.get("provider", "unknown"))
            discovered, discovery = discovery_jobs(input_path, now, profile)
            review.extend(discovery.pop("review", []))
            jobs.extend(discovered)
            if not reports and not discovered:
                raise ValueError("Nenhuma fonte respondeu; a rodada não foi marcada como concluída.")
            unique = {job["source_url"]: job for job in jobs}
            selected = prioritize(list(unique.values()), 50, profile)
            write_json(RUNTIME / "daily-review.json", {"checked_at": now.isoformat(), "jobs": review})
            endpoint = local_api_url(config.get("JOB_RADAR_API_URL"))
            key = config.get("INGEST_API_KEY")
            if not key:
                raise ValueError("Chave de ingestão não configurada.")
            existing = list_existing(client, endpoint)
            pending = state.get("pending_new_jobs", [])
            new_jobs = [item for item in pending if isinstance(item, dict)]
            matched_jobs = []
            for job in selected:
                response = client.post(endpoint + "/api/v1/jobs", json=job, headers={"X-API-Key": key})
                response.raise_for_status()
                saved = response.json()
                matched_jobs.append({name: saved[name] for name in ("id", "title", "company", "source_url")})
                if job["source_url"] not in existing:
                    new_jobs.append({name: saved[name] for name in
                                     ("id", "title", "company", "source_url")})
                    existing[job["source_url"]] = saved["id"]
                    state["pending_new_jobs"] = new_jobs
                    write_json(state_path, state)
        report = {"status": "partial" if failures else "completed", "slot": slot,
                  "checked_at": now.isoformat(), "selected": len(selected), "new_jobs": new_jobs,
                  "matched_jobs": matched_jobs,
                  "sources": reports, "failed_sources": failures, "discovery": discovery,
                  "minimum_results": target, "meets_target": len(selected) >= target,
                  "shortfall": max(0, target - len(selected)), "review_count": len(review)}
        # Persistir antes da chamada remota evita reenvio automático após resposta ambígua.
        should_notify = notify and (state.get("notification_slot") != slot or bool(new_jobs))
        state.update({"completed_slot": slot, "report": report})
        state.pop("pending_new_jobs", None)
        if should_notify:
            state.update({"notification_slot": slot, "notification_status": "sending"})
        write_json(state_path, state)
        if should_notify:
            try:
                result = send_notification(config, digest(report))
                state.update({"notification_status": "sent", "message_id": result.get("message_id")})
            except ValueError:
                state["notification_status"] = "unconfirmed"
            write_json(state_path, state)
        return {**report, "notification_status": state.get("notification_status", "disabled")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true")
    group.add_argument("--scheduled", action="store_true")
    group.add_argument("--run-now", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--no-notify", action="store_true", help="Validação local sem enviar aviso")
    args = parser.parse_args()
    try:
        if args.status:
            state = read_state(RUNTIME / "daily-state.json")
            slot = scheduled_slot(datetime.now(timezone.utc))
            result = {"slot": slot, "due": state.get("completed_slot", "") < slot,
                      "completed_slot": state.get("completed_slot"),
                      "notification_status": state.get("notification_status")}
        else:
            if args.input:
                source = args.input.resolve()
                if RUNTIME.resolve() not in source.parents or source.suffix != ".json":
                    raise ValueError("A descoberta deve ser um JSON dentro de .runtime.")
            result = run_once(dotenv_values(ROOT / ".env"), force=args.run_now,
                              input_path=args.input, notify=not args.no_notify)
        print(json.dumps(result, ensure_ascii=True))
    except (ValueError, KeyError, TypeError, OSError, httpx.HTTPError):
        parser.exit(1, "A busca não pôde ser concluída. Confira os serviços e fontes; nenhuma credencial foi exibida.\n")


if __name__ == "__main__":
    main()
