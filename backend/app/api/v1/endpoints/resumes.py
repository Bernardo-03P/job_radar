from hashlib import sha256
from io import BytesIO
from typing import Annotated
from uuid import UUID

from agent.formal_activity import formal_activity
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db.session import get_db
from app.schemas.resume import (
    SavedResumeRead,
    SavedSourceTailorRequest,
    TailorResponse,
    TailorResponseData,
)
from app.services import resume_store, resume_vault
from app.services.generation_lock import database_generation_lease, generation_lock
from app.services.llm_client import LLMService
from app.services.pdf_parser import PDFParserService
from app.services.resume_tailor import ResumeTailorService


class MemoryFormRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def memory_handler(request):
            request._form = request.scope.get("state", {}).get("memory_form")
            return await handler(request)

        return memory_handler


router = APIRouter(route_class=MemoryFormRoute)


@router.post("/sources", status_code=201)
async def store_original(resume_file: Annotated[UploadFile, File()],
                         x_resume_token: Annotated[str | None, Header()] = None):
    try:
        resume_store.owner_hash(x_resume_token)
        if not (resume_file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "Apenas formato PDF é suportado.")
        await PDFParserService.extract_text_from_pdf(resume_file)
        await resume_file.seek(0)
        pdf = await resume_file.read(5 * 1024 * 1024 + 1)
        return await run_in_threadpool(resume_vault.save_source, pdf, resume_file.filename, x_resume_token)
    finally:
        await resume_file.close()


@router.get("/sources")
def sources(x_resume_token: Annotated[str | None, Header()] = None,
            x_api_key: Annotated[str | None, Header()] = None):
    return resume_vault.list_sources(x_resume_token, x_api_key)


@router.delete("/sources/{source_id}", status_code=204)
def remove_original(source_id: UUID, x_resume_token: Annotated[str | None, Header()] = None,
                    x_api_key: Annotated[str | None, Header()] = None):
    resume_vault.delete_source(str(source_id), x_resume_token, x_api_key)


@router.post("/tailor-saved", response_model=TailorResponse)
async def tailor_saved(payload: SavedSourceTailorRequest,
                       db: Annotated[Session, Depends(get_db)],
                       llm: Annotated[LLMService, Depends()],
                       x_api_key: Annotated[str | None, Header()] = None):
    import base64

    from app.models.job import Job
    if not resume_vault.is_admin(x_api_key):
        raise HTTPException(401, "A geração pelo bot exige acesso privado.")
    record = await run_in_threadpool(resume_vault.read_source, str(payload.source_id), None, x_api_key)
    job = await run_in_threadpool(db.get, Job, payload.job_id)
    if job is None:
        raise HTTPException(404, "Vaga não encontrada.")
    if len(job.description) > 30000:
        raise HTTPException(422, "Descrição excede o limite para adaptação.")
    upload = UploadFile(BytesIO(base64.b64decode(record["pdf"])), filename="original.pdf")
    return await tailor_resume(upload, job.description, llm, db, job.id, record["token"])


@router.post("/tailor", response_model=TailorResponse)
async def tailor_resume(resume_file: Annotated[UploadFile, File()],
                        job_description: Annotated[str, Form(min_length=20, max_length=30000)],
                        llm: Annotated[LLMService, Depends()],
                        db: Annotated[Session, Depends(get_db)],
                        job_id: Annotated[int | None, Form(ge=1)] = None,
                        x_resume_token: Annotated[str | None, Header()] = None):
    try:
        with formal_activity():
            if not (resume_file.filename or "").lower().endswith(".pdf"):
                raise HTTPException(400, "Apenas formato PDF é suportado.")
            if not job_description.strip():
                raise HTTPException(422, "Informe a descrição da vaga.")
            owner = resume_store.owner_hash(x_resume_token)
            raw = await PDFParserService.extract_text_from_pdf(resume_file)
            await resume_file.seek(0)
            fingerprint = sha256(await resume_file.read(5 * 1024 * 1024 + 1)).hexdigest()
            context = resume_store.context_hash(job_id, job_description)
            async with generation_lock(f"{owner}:{fingerprint}:{context}"):
                title, company = await run_in_threadpool(resume_store.job_metadata, db, job_id)
                previous = await run_in_threadpool(
                    resume_store.find_version, db, owner, fingerprint, context
                )
                if previous is not None:
                    response = TailorResponse(data=TailorResponseData.model_validate(previous.data),
                                             version=SavedResumeRead.model_validate(previous), cached=True)
                    await run_in_threadpool(db.rollback)
                    return response
                # Libere a conex?o/transaction antes de aguardar a API externa.
                await run_in_threadpool(db.rollback)
                async with database_generation_lease(db, f"{owner}:{fingerprint}:{context}"):
                    # Outro processo pode ter conclu?do entre o primeiro SELECT e o lock.
                    previous = await run_in_threadpool(resume_store.find_version, db, owner, fingerprint, context)
                    if previous is not None:
                        response = TailorResponse(data=TailorResponseData.model_validate(previous.data),
                                                 version=SavedResumeRead.model_validate(previous), cached=True)
                        await run_in_threadpool(db.rollback)
                        return response
                    await run_in_threadpool(db.rollback)
                    data = await ResumeTailorService.generate_validated(llm, raw, job_description)
                    saved = await run_in_threadpool(resume_store.save_version, db, owner, fingerprint,
                                                   context, job_id, job_description, title, company, data)
                    return TailorResponse(data=data, version=SavedResumeRead.model_validate(saved))
    finally:
        await resume_file.close()


@router.get("/versions", response_model=list[SavedResumeRead])
def list_versions(db: Annotated[Session, Depends(get_db)],
                  x_resume_token: Annotated[str | None, Header()] = None,
                  x_api_key: Annotated[str | None, Header()] = None,
                  job_id: int | None = None, q: str = "", before_id: UUID | None = None,
                  limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    from app.models.resume_version import ResumeVersion
    statement = resume_store.version_scope(x_resume_token, x_api_key)
    if before_id is not None:
        cursor = owned_version(db, str(before_id), x_resume_token, x_api_key)
        statement = statement.where(or_(
            ResumeVersion.created_at < cursor.created_at,
            and_(ResumeVersion.created_at == cursor.created_at, ResumeVersion.id < cursor.id),
        ))
    if job_id is not None:
        statement = statement.where(ResumeVersion.job_id == job_id)
    if q:
        statement = statement.where(ResumeVersion.job_title.icontains(q[:200], autoescape=True))
    statement = statement.order_by(ResumeVersion.created_at.desc(), ResumeVersion.id.desc()).offset(offset).limit(limit)
    return db.scalars(statement).all()


def owned_version(db, version_id, token, api_key):
    from app.models.resume_version import ResumeVersion
    statement = resume_store.version_scope(token, api_key).where(ResumeVersion.id == version_id)
    version = db.scalar(statement)
    if version is None:
        raise HTTPException(404, "Versão não encontrada.")
    return version


@router.get("/versions/{version_id}", response_model=SavedResumeRead)
def read_version(version_id: str, db: Annotated[Session, Depends(get_db)],
                 x_resume_token: Annotated[str | None, Header()] = None,
                 x_api_key: Annotated[str | None, Header()] = None):
    return owned_version(db, version_id, x_resume_token, x_api_key)


@router.get("/versions/{version_id}/markdown")
def download_version(version_id: str, db: Annotated[Session, Depends(get_db)],
                     x_resume_token: Annotated[str | None, Header()] = None,
                     x_api_key: Annotated[str | None, Header()] = None):
    version = owned_version(db, version_id, x_resume_token, x_api_key)
    return PlainTextResponse(version.data["adapted_resume_markdown"], media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="curriculo-{version.id}.md"'})


@router.delete("/versions/{version_id}", status_code=204)
def delete_version(version_id: str, db: Annotated[Session, Depends(get_db)],
                   x_resume_token: Annotated[str | None, Header()] = None,
                   x_api_key: Annotated[str | None, Header()] = None):
    db.delete(owned_version(db, version_id, x_resume_token, x_api_key))
    db.commit()
