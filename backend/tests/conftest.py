import socket
from io import BytesIO

import pymupdf as fitz
import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from main import app


@pytest.fixture(autouse=True)
def isolate_formal_activity(tmp_path, mocker):
    mocker.patch('agent.formal_activity.RUNTIME', tmp_path / 'activity')


@pytest.fixture(autouse=True)
def block_network(mocker):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded(original):
        def connect(instance, address):
            if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
                return original(instance, address)
            raise AssertionError("Chamadas externas bloqueadas no CI")
        return connect

    mocker.patch.object(socket.socket, "connect", guarded(original_connect))
    mocker.patch.object(socket.socket, "connect_ex", guarded(original_connect_ex))
    mocker.patch.object(settings, "groq_api_key", "")
    mocker.patch.object(settings, "openai_api_key", "")


@pytest.fixture
def pdf_bytes():
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Ana Silva\nPython e FastAPI\nEmpresa Real - 2022 a 2024")
        return document.tobytes()


@pytest.fixture
def upload(pdf_bytes):
    return UploadFile(BytesIO(pdf_bytes), filename="curriculo.pdf")


@pytest.fixture(autouse=True)
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()
