import asyncio
import json
import os
import sys
from contextlib import suppress
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile

MAX_SIZE = 5 * 1024 * 1024


class PDFParserService:
    @staticmethod
    async def extract_text_from_pdf(file: UploadFile) -> str:
        contents = await file.read(MAX_SIZE + 1)
        if len(contents) > MAX_SIZE:
            raise HTTPException(400, "Arquivo excede o limite de 5MB.")
        if not contents.startswith(b"%PDF-"):
            raise HTTPException(400, "Arquivo PDF inválido.")
        from app.core.config import settings
        environment = {key: value for key, value in os.environ.items()
                       if not key.upper().endswith(("API_KEY", "TOKEN"))}
        environment.update({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
        worker = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.services.pdf_worker",
            cwd=Path(__file__).resolve().parents[2], env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        try:
            output, _ = await asyncio.wait_for(worker.communicate(contents), settings.pdf_timeout_seconds)
            if worker.returncode or len(output) > 300000:
                raise HTTPException(400, "O PDF excede os limites seguros de processamento.")
            try:
                result = json.loads(output)
                if result.get("status") != 200:
                    raise HTTPException(400, result.get("detail", "Não foi possível ler o PDF."))
                text = result["text"]
                if not isinstance(text, str) or not text.strip() or len(text) > 60000:
                    raise ValueError()
                return text
            except (ValueError, KeyError, AttributeError):
                raise HTTPException(400, "Não foi possível ler o PDF.") from None
        except TimeoutError:
            raise HTTPException(400, "O PDF excede o tempo seguro de processamento.") from None
        finally:
            if worker.returncode is None:
                with suppress(ProcessLookupError):
                    worker.kill()
                await worker.wait()

    @staticmethod
    def _extract(contents: bytes) -> str:
        import pymupdf as fitz
        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)
        try:
            with fitz.open(stream=BytesIO(contents), filetype="pdf") as doc:
                if doc.needs_pass:
                    raise HTTPException(400, "PDF protegido por senha não é suportado.")
                if len(doc) > 100:
                    raise HTTPException(400, "O currículo deve ter no máximo 100 páginas.")
                parts = []
                length = 0
                for page in doc:
                    part = page.get_text()
                    length += len(part) + 1
                    if length > 60001:
                        raise HTTPException(400, "O currículo excede o limite de texto.")
                    parts.append(part)
                text = "\n".join(parts).strip()
                if not text:
                    raise HTTPException(400, "O PDF não contém texto extraível.")
                if len(text) > 60000:
                    raise HTTPException(400, "O currículo excede o limite de texto.")
                return text
        except HTTPException:
            raise
        except (RuntimeError, ValueError):
            raise HTTPException(400, "Não foi possível ler o PDF.") from None
