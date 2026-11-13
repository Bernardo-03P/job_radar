from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import initialize_database
from app.services.memory_upload import MemoryUploadMiddleware


@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(initialize_database)
    yield


app = FastAPI(title="Tech Job Radar & Tailored Resume Matcher", lifespan=lifespan)
app.add_middleware(MemoryUploadMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Content-Type", "X-API-Key", "X-Resume-Token"])
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def privacy_headers(request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        # Não registre exceções brutas: provedores podem incluir conteúdo pessoal.
        response = JSONResponse({"detail": "Erro interno ao processar a solicitação."}, 500)
        origin = request.headers.get("origin")
        if origin in settings.cors_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/v1/resumes"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse({"detail": "Banco de dados indisponível."}, status_code=503)


@app.get("/health")
async def health():
    return {"status": "ok"}
