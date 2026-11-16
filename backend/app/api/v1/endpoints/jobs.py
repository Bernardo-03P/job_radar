import secrets
from typing import Annotated

from agent.job_profile import load_profile, schedule_group, stage
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobRead, canonical_source_url

router = APIRouter()


@router.get("", response_model=list[JobRead])
def list_jobs(db: Annotated[Session, Depends(get_db)], q: str = "",
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              matching_profile: bool = False, include_unconfirmed_hours: bool = False):
    statement = select(Job).order_by(Job.created_at.desc(), Job.id.desc())
    if q:
        query = q[:200]
        statement = statement.where(or_(Job.title.icontains(query, autoescape=True),
                                        Job.company.icontains(query, autoescape=True)))
    if matching_profile:
        profile = load_profile()
        unique = {}
        for job in db.scalars(statement):
            group = schedule_group({"title": job.title, "description": job.description,
                                    "location": job.location}, profile)
            if group is None or group == 'unconfirmed' and not include_unconfirmed_hours:
                continue
            key = canonical_source_url(job.source_url)
            if key not in unique or job.id < unique[key].id:
                unique[key] = job
        matches = sorted(unique.values(), key=lambda job: (job.created_at, job.id), reverse=True)
        matches.sort(key=lambda job: (schedule_group({'title': job.title, 'description': job.description,
                                                     'location': job.location}, profile) != 'confirmed',
                                      stage({"title": job.title}) != "internship"))
        return [JobRead.model_validate(job).model_copy(update={'schedule_status': schedule_group(
            {'title': job.title, 'description': job.description, 'location': job.location}, profile)})
                for job in matches[offset:offset + limit]]
    return db.scalars(statement.offset(offset).limit(limit)).all()


@router.post("", response_model=JobRead, status_code=201)
def ingest_job(payload: JobCreate, db: Annotated[Session, Depends(get_db)],
               x_api_key: Annotated[str | None, Header()] = None):
    if not settings.ingest_api_key or not secrets.compare_digest(
        (x_api_key or "").encode(), settings.ingest_api_key.encode()
    ):
        raise HTTPException(401, "Chave de ingestão inválida.")
    record = payload.model_dump(mode="json")
    existing = db.scalar(select(Job).where(Job.source_url == record["source_url"]))
    job = existing or Job(**record)
    if existing:
        for key, value in record.items():
            setattr(job, key, value)
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Vaga já recebida; tente novamente.") from None
    return job
