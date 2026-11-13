"""Deduplicação por chave, sem manter locks ociosos nem misturar event loops."""
import asyncio
from contextlib import asynccontextmanager
from hashlib import sha256
from threading import Lock
from weakref import WeakKeyDictionary

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

_loops = WeakKeyDictionary()


class DatabaseGenerationLease:
    """Proteção entre processos PostgreSQL, em conexão sem transação aberta."""
    def __init__(self, db, key):
        self.engine = db.get_bind()
        self.key = int.from_bytes(sha256(key.encode()).digest()[:8], "big", signed=True)
        self.connection = None
        self.lock = Lock()

    def acquire(self):
        if self.engine.dialect.name != "postgresql":
            return
        with self.lock:
            connection = self.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            try:
                acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": self.key})
            except BaseException:
                connection.invalidate()
                connection.close()
                raise
            if not acquired:
                connection.close()
                raise HTTPException(409, "Esta versão está sendo gerada por outra solicitação. Aguarde e consulte o histórico.")
            self.connection = connection

    def release(self):
        with self.lock:
            if self.connection is not None:
                try:
                    self.connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.key})
                except SQLAlchemyError:
                    self.connection.invalidate()
                finally:
                    self.connection.close()
                    self.connection = None


@asynccontextmanager
async def database_generation_lease(db, key):
    lease = DatabaseGenerationLease(db, key)
    try:
        await run_in_threadpool(lease.acquire)
        yield
    finally:
        await asyncio.shield(run_in_threadpool(lease.release))


@asynccontextmanager
async def generation_lock(key: str):
    loop = asyncio.get_running_loop()
    locks = _loops.setdefault(loop, {})
    entry = locks.setdefault(key, {"lock": asyncio.Lock(), "users": 0})
    entry["users"] += 1
    acquired = False
    try:
        await entry["lock"].acquire()
        acquired = True
        yield
    finally:
        if acquired:
            entry["lock"].release()
        entry["users"] -= 1
        if not entry["users"]:
            del locks[key]
        if not locks:
            _loops.pop(loop, None)
