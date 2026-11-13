from io import BytesIO

import pymupdf as fitz
import pytest
from fastapi import HTTPException, UploadFile

from app.services.pdf_parser import MAX_SIZE, PDFParserService


async def test_extract_text(upload):
    assert "Ana Silva" in await PDFParserService.extract_text_from_pdf(upload)


@pytest.mark.parametrize("payload", [b"", b"not-pdf", b"%PDF-1.4 broken"])
async def test_invalid_pdf(payload):
    with pytest.raises(HTTPException) as error:
        await PDFParserService.extract_text_from_pdf(UploadFile(BytesIO(payload)))
    assert error.value.status_code == 400


async def test_empty_pdf():
    with fitz.open() as document:
        document.new_page()
        payload = document.tobytes()
    with pytest.raises(HTTPException) as error:
        await PDFParserService.extract_text_from_pdf(UploadFile(BytesIO(payload)))
    assert error.value.status_code == 400
    assert "texto extraível" in error.value.detail


async def test_oversized_pdf():
    with pytest.raises(HTTPException) as error:
        await PDFParserService.extract_text_from_pdf(UploadFile(BytesIO(b"x" * (MAX_SIZE + 1))))
    assert error.value.status_code == 400
