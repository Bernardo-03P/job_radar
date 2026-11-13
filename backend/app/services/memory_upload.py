"""Multipart limitado e incremental: buffers BytesIO, sem spool em disco."""
import asyncio
from io import BytesIO
from threading import Lock

from fastapi import HTTPException, UploadFile
from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData, Headers
from starlette.responses import JSONResponse

from app.core.config import settings
from app.services.pdf_parser import MAX_SIZE
from app.services.resume_store import owner_hash
from app.services.resume_vault import is_admin

MAX_BODY = MAX_SIZE + 128 * 1024


async def bounded_json(scope, receive):
    headers = Headers(scope=scope)
    if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Envie a seleção em JSON.")
    lengths = headers.getlist("content-length")
    if len(lengths) > 1 or (lengths and (not lengths[0].isascii() or not lengths[0].isdigit())):
        raise HTTPException(400, "Tamanho da seleção inválido.")
    expected = int(lengths[0]) if lengths else None
    if expected is not None and expected > 4096:
        raise HTTPException(413, "Seleção excede o limite permitido.")
    body = bytearray()
    async with asyncio.timeout(settings.upload_timeout_seconds):
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise HTTPException(400, "Seleção interrompida.")
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 4096:
                raise HTTPException(413, "Seleção excede o limite permitido.")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
    if expected is not None and len(body) != expected:
        raise HTTPException(400, "Seleção incompleta.")
    return bytes(body)


class MemoryFormParser:
    def __init__(self):
        self.values = []
        self.buffers = []
        self.headers = {}
        self.header_name = bytearray()
        self.header_value = bytearray()
        self.header_bytes = 0
        self.name = ""
        self.filename = None
        self.buffer = None
        self.ended = False

    def part_begin(self):
        if len(self.values) >= 3:
            raise HTTPException(400, "Campos multipart inválidos.")
        self.headers = {}
        self.header_bytes = 0
        self.buffer = BytesIO()
        self.buffers.append(self.buffer)

    def header_field(self, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise HTTPException(400, "Cabeçalho multipart excede o limite.")
        self.header_name.extend(data[start:end])

    def header_data(self, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise HTTPException(400, "Cabeçalho multipart excede o limite.")
        self.header_value.extend(data[start:end])

    def header_end(self):
        name = bytes(self.header_name).lower()
        if name in self.headers:
            raise HTTPException(400, "Cabeçalho multipart duplicado.")
        self.headers[name] = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def headers_finished(self):
        disposition, options = parse_options_header(self.headers.get(b"content-disposition", b""))
        self.name = options.get(b"name", b"").decode("utf-8")
        self.filename = options.get(b"filename")
        if (disposition != b"form-data" or self.name not in {"resume_file", "job_description", "job_id"}
                or any(name == self.name for name, _ in self.values)):
            raise HTTPException(400, "Campos multipart inválidos ou duplicados.")
        if (self.name == "resume_file") != (self.filename is not None):
            raise HTTPException(400, "Campo de arquivo inválido.")

    def part_data(self, data, start, end):
        limit = MAX_SIZE if self.filename is not None else (120000 if self.name == "job_description" else 20)
        if self.buffer.tell() + end - start > limit:
            raise HTTPException(400, "Arquivo excede o limite de 5MB ou campo de texto excede o limite.")
        self.buffer.write(data[start:end])

    def part_end(self):
        if self.filename is not None:
            self.buffer.seek(0)
            value = UploadFile(self.buffer, filename=self.filename.decode("utf-8", errors="replace"),
                               size=len(self.buffer.getbuffer()), headers=Headers({
                                   "content-type": self.headers.get(b"content-type", b"application/pdf").decode("latin-1")
                               }))
        else:
            value = self.buffer.getvalue().decode("utf-8")
        self.values.append((self.name, value))

    def end(self):
        self.ended = True

    def close(self):
        for buffer in self.buffers:
            buffer.close()

    async def parse(self, scope, receive):
        headers = Headers(scope=scope)
        content_type, options = parse_options_header(headers.get("content-type", ""))
        boundary = options.get(b"boundary", b"")
        if (content_type != b"multipart/form-data" or not 1 <= len(boundary) <= 70
                or any(byte < 32 or byte > 126 for byte in boundary)):
            raise HTTPException(400, "Formulário multipart inválido.")
        lengths = headers.getlist("content-length")
        if len(lengths) > 1 or (lengths and not lengths[0].isascii()) or (lengths and not lengths[0].isdigit()):
            raise HTTPException(400, "Tamanho de upload inválido.")
        expected = int(lengths[0]) if lengths else None
        if expected is not None and expected > MAX_BODY:
            raise HTTPException(413, "Upload excede o limite permitido.")
        parser = MultipartParser(boundary, {
            "on_part_begin": self.part_begin, "on_header_field": self.header_field,
            "on_header_value": self.header_data, "on_header_end": self.header_end,
            "on_headers_finished": self.headers_finished, "on_part_data": self.part_data,
            "on_part_end": self.part_end, "on_end": self.end,
        })
        consumed = 0
        async with asyncio.timeout(settings.upload_timeout_seconds):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    raise HTTPException(400, "Upload interrompido.")
                chunk = message.get("body", b"")
                consumed += len(chunk)
                if consumed > MAX_BODY:
                    raise HTTPException(413, "Upload excede o limite permitido.")
                parser.write(chunk)
                if not message.get("more_body", False):
                    break
        parser.finalize()
        if not self.ended or (expected is not None and consumed != expected):
            raise HTTPException(400, "Formulário multipart incompleto.")
        return FormData(self.values)


class MemoryUploadMiddleware:
    def __init__(self, app):
        self.app = app
        self.active = 0
        self.lock = Lock()

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope.get("method") != "POST"
                or scope["path"].rstrip("/") not in
                {"/api/v1/resumes/tailor", "/api/v1/resumes/sources", "/api/v1/resumes/tailor-saved"}):
            return await self.app(scope, receive, send)
        saved = scope["path"].rstrip("/") == "/api/v1/resumes/tailor-saved"
        try:
            if saved:
                if not is_admin(Headers(scope=scope).get("x-api-key")):
                    raise HTTPException(401, "A geração pelo bot exige acesso privado.")
            else:
                owner_hash(Headers(scope=scope).get("x-resume-token"))
        except HTTPException as error:
            return await JSONResponse({"detail": error.detail}, error.status_code)(scope, receive, send)
        with self.lock:
            admitted = self.active < settings.max_concurrent_uploads
            if admitted:
                self.active += 1
        if not admitted:
            return await JSONResponse({"detail": "Há muitos uploads em processamento. Tente novamente."},
                                      429, headers={"Retry-After": "5"})(scope, receive, send)
        form_parser = None if saved else MemoryFormParser()
        try:
            try:
                if saved:
                    body = await bounded_json(scope, receive)
                else:
                    form = await form_parser.parse(scope, receive)
            except HTTPException as error:
                return await JSONResponse({"detail": error.detail}, error.status_code)(scope, receive, send)
            except TimeoutError:
                return await JSONResponse({"detail": "Tempo limite para receber o upload."}, 408)(scope, receive, send)
            except (ValueError, UnicodeError):
                return await JSONResponse({"detail": "Formulário multipart inválido."}, 400)(scope, receive, send)
            if saved:
                consumed = False

                async def replay():
                    nonlocal consumed
                    if not consumed:
                        consumed = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                await self.app(scope, replay, send)
            else:
                scope["state"] = {**scope.get("state", {}), "memory_form": form}
                await self.app(scope, receive, send)
        finally:
            if form_parser is not None:
                form_parser.close()
            with self.lock:
                self.active -= 1
