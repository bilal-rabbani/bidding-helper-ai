"""Reads a PDF page by page, keeping the page number with the text."""
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

MIN_CHARS_FOR_TEXT_LAYER = 50


@dataclass
class PageText:
    page_no: int          # 1-based, as shown in a PDF viewer
    text: str
    has_text_layer: bool  # False means the page is probably scanned (OCR needed)


def read_pages(path) -> list:
    """Return the text of every page. Pages with almost no text are marked."""
    pages = []
    with pdfplumber.open(Path(path)) as doc:
        for i, page in enumerate(doc.pages, start=1):
            text = page.extract_text() or ""
            pages.append(PageText(i, text, len(text.strip()) >= MIN_CHARS_FOR_TEXT_LAYER))
            page.close()
    return pages
