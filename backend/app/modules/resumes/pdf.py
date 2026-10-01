"""PDF validation and text extraction. Uploaded files are untrusted input."""

import io
import logging
import re
from dataclasses import dataclass

import pdfplumber
from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"
MAX_TEXT_CHARS = 30_000  # ~7.5k tokens: plenty for any resume, bounded for the LLM

# pdfminer is very chatty about malformed-but-readable PDFs.
logging.getLogger("pdfminer").setLevel(logging.ERROR)


class InvalidPdfError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PdfInfo:
    page_count: int


def inspect_pdf(data: bytes, *, max_pages: int) -> PdfInfo:
    # Check the real content, not the filename or the client's Content-Type.
    if not data.lstrip()[:1024].startswith(PDF_MAGIC):
        raise InvalidPdfError("This file isn't a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise InvalidPdfError(
                "Password-protected PDFs aren't supported. Please remove the password."
            )
        pages = len(reader.pages)
    except PdfReadError as exc:
        raise InvalidPdfError("This PDF looks damaged and can't be read.") from exc
    if pages == 0:
        raise InvalidPdfError("This PDF has no pages.")
    if pages > max_pages:
        raise InvalidPdfError(f"Resumes can be at most {max_pages} pages (this one has {pages}).")
    return PdfInfo(page_count=pages)


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t\u00a0]+", " ", text)  # spaces, tabs, non-breaking spaces
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def extract_text(data: bytes) -> str:
    """pdfplumber keeps layout (columns, bullets) best; pypdf is the fallback."""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join(page.extract_text(x_tolerance=1.5) or "" for page in pdf.pages)
        if len(text.strip()) >= 50:
            return _clean(text)
    except Exception:  # noqa: S110 - fall through to the second extractor
        pass
    try:
        reader = PdfReader(io.BytesIO(data))
        return _clean("\n".join(page.extract_text() or "" for page in reader.pages))
    except Exception:
        return ""
