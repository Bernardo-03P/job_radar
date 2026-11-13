"""PDF original opcional, protegido por DPAPI do usuário atual do Windows."""
import base64
import ctypes
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from app.core.config import settings
from app.services.pdf_parser import MAX_SIZE
from app.services.resume_store import owner_hash

VAULT = Path(__file__).resolve().parents[3] / ".runtime/resume-vault"
MAX_BLOB = 8 * 1024 * 1024


def protect(data, decrypt=False):
    if os.name != "nt":
        raise HTTPException(503, "Guardar o original requer a proteção do usuário do Windows.")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise HTTPException(503, "Não foi possível acessar a proteção local do Windows.")
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.memset(buffer, 0, len(buffer))
        if output.data:
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)


def source_path(identifier):
    try:
        identifier = str(UUID(str(identifier)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "PDF guardado não encontrado.") from None
    path = VAULT / (identifier + ".bin")
    if path.is_symlink():
        raise HTTPException(404, "PDF guardado não encontrado.")
    return path


def is_admin(api_key):
    if not api_key:
        return False
    if not settings.resume_api_key or not secrets.compare_digest(
            api_key.encode(), settings.resume_api_key.encode()):
        raise HTTPException(401, "Chave privada inválida.")
    return True


def metadata(record):
    return {key: record[key] for key in ("id", "filename", "fingerprint", "created_at")}


def read_source(identifier, token=None, api_key=None):
    admin = is_admin(api_key)
    owner = None if admin else owner_hash(token)
    path = source_path(identifier)
    try:
        if path.stat().st_size > MAX_BLOB:
            raise ValueError()
        record = json.loads(protect(path.read_bytes(), decrypt=True))
        if record["id"] != str(UUID(str(identifier))):
            raise ValueError()
        if not admin and record["owner_hash"] != owner:
            raise HTTPException(404, "PDF guardado não encontrado.")
        if owner_hash(record["token"]) != record["owner_hash"]:
            raise ValueError()
        pdf = base64.b64decode(record["pdf"], validate=True)
        if len(pdf) > MAX_SIZE or sha256(pdf).hexdigest() != record["fingerprint"]:
            raise ValueError()
        return record
    except FileNotFoundError:
        raise HTTPException(404, "PDF guardado não encontrado.") from None
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "O PDF guardado está indisponível; envie-o novamente pelo site.") from None


def save_source(pdf, filename, token):
    owner = owner_hash(token)
    if not pdf.startswith(b"%PDF-") or len(pdf) > MAX_SIZE:
        raise HTTPException(400, "PDF inválido ou maior que 5 MiB.")
    identifier = str(UUID(owner[:32]))
    path = source_path(identifier)
    VAULT.mkdir(parents=True, exist_ok=True)
    if not path.exists() and len(list(VAULT.glob("*.bin"))) >= 20:
        raise HTTPException(409, "Limite de PDFs guardados atingido; exclua um original antes de continuar.")
    record = {"id": identifier, "owner_hash": owner, "token": token,
              "filename": filename.replace("\\", "/").split("/")[-1][:100],
              "fingerprint": sha256(pdf).hexdigest(), "created_at": datetime.now(timezone.utc).isoformat(),
              "pdf": base64.b64encode(pdf).decode("ascii")}
    encrypted = protect(json.dumps(record).encode("utf-8"))
    descriptor, name = tempfile.mkstemp(prefix="source-", suffix=".tmp", dir=VAULT)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return metadata(record)


def list_sources(token=None, api_key=None):
    if not is_admin(api_key):
        identifier = str(UUID(owner_hash(token)[:32]))
        if not source_path(identifier).exists():
            return []
        return [metadata(read_source(identifier, token))]
    return [metadata(read_source(path.stem, api_key=api_key)) for path in sorted(VAULT.glob("*.bin"))]


def delete_source(identifier, token=None, api_key=None):
    read_source(identifier, token, api_key)
    source_path(identifier).unlink(missing_ok=True)
