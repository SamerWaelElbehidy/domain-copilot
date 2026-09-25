from __future__ import annotations

from abc import ABC, abstractmethod


class PdfTextExtractor(ABC):
    @abstractmethod
    def extract_pages(self, pdf_bytes: bytes) -> list[str]:
        """One text string per page. Raises UnsupportedDocumentError for
        damaged, encrypted or oversized files."""
        ...
