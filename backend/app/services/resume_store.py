import hashlib
import json
import re
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.schemas.resume import TailorResponseData


def owner_hash(token: str | None) -> str:
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{32,160}", token):
        raise HTTPException(401, "Identificação privada do histórico ausente ou inválida.")
    return hashlib.sha256(token.encode()).hexdigest()


def version_scope(token: str | None, api_key: str | None):
    if api_key:
        if not settings.resume_api_key or not secrets.compare_digest(api_key.encode(), settings.resume_api_key.encode()):
            raise HTTPException(401, "Chave de acesso aos currículos inválida.")
        return select(ResumeVersion)
    return select(ResumeVersion).where(ResumeVersion.owner_hash == owner_hash(token))


def context_hash(job_id: int | None, description: str) -> str:
    value = json.dumps([job_id, description], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def find_version(db: Session, owner: str, fingerprint: str, context: str):
    return db.scalar(select(ResumeVersion).where(
        ResumeVersion.owner_hash == owner,
        ResumeVersion.source_fingerprint == fingerprint,
        ResumeVersion.context_hash == context,
    ))


def job_metadata(db: Session, job_id: int | None):
    if job_id is None:
        return "Descrição personalizada", ""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Vaga não encontrada.")
    return job.title, job.company


def save_version(db: Session, owner: str, fingerprint: str, context: str,
                 job_id: int | None, description: str, title: str, company: str,
                 data: TailorResponseData):
    version = ResumeVersion(owner_hash=owner, source_fingerprint=fingerprint,
                            context_hash=context, job_id=job_id, job_title=title,
                            company=company, job_description=description,
                            data=data.model_dump())
    db.add(version)
    try:
        db.commit()
        db.refresh(version)
    except IntegrityError:
        db.rollback()
        existing = find_version(db, owner, fingerprint, context)
        if existing is None:
            raise
        return existing
    return version
