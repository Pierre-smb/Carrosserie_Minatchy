from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def extract_pages_text(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]

