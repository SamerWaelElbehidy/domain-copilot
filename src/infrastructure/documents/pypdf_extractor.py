from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from application.ports.pdf_text_extractor import PdfTextExtractor
from domain.errors.domain_errors import UnsupportedDocumentError

MAX_PAGES = 500


class PypdfTextExtractor(PdfTextExtractor):
    """PDF text extraction with pypdf (pure Python, no native code).
    Encrypted and oversized files are refused rather than processed."""

    def __init__(self, max_pages: int = MAX_PAGES) -> None:
        self._max_pages = max_pages

    def extract_pages(self, pdf_bytes: bytes) -> list[str]:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            if reader.is_encrypted:
                raise UnsupportedDocumentError("encrypted PDFs are not accepted")
            if len(reader.pages) > self._max_pages:
                raise UnsupportedDocumentError(
                    f"PDF has {len(reader.pages)} pages; the limit is {self._max_pages}"
                )
            return [page.extract_text() or "" for page in reader.pages]
        except UnsupportedDocumentError:
            raise
        except (PyPdfError, ValueError, KeyError, OSError, RecursionError) as exc:
            raise UnsupportedDocumentError(f"PDF could not be read: {exc}") from exc
