import secrets
from typing import Annotated

from agent.job_profile import load_profile, profile_match, stage
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobRead

router = APIRouter()


@router.get("", response_model=list[JobRead])
def list_jobs(db: Annotated[Session, Depends(get_db)], q: str = "",
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              matching_profile: bool = False):
    statement = select(Job).order_by(Job.created_at.desc(), Job.id.desc())
    if q:
        query = q[:200]
        statement = statement.where(or_(Job.title.icontains(query, autoescape=True),
                                        Job.company.icontains(query, autoescape=True)))
    if matching_profile:
        profile = load_profile()
        matches = [job for job in db.scalars(statement)
                   if profile_match({"title": job.title, "description": job.description,
                                     "location": job.location}, profile)[0]]
        matches.sort(key=lambda job: stage({"title": job.title}) != "internship")
        return matches[offset:offset + limit]
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
