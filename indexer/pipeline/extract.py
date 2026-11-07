"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page.

Design notes (see docs/PIPELINE.md):
* PDFs go through pdfplumber. A page whose text layer is (almost) empty is rasterised and
  OCR'd with Tesseract, and marked ocr=True.
* Tables found by pdfplumber are removed from the running text and re-emitted as
  pipe-separated rows ("| a | b |"), so columns stay aligned instead of being jumbled.
* HTML pages keep their <table> rows as pipe rows too; Markdown is read as it is.
* Memory: one page at a time, and pdfplumber's per-page cache is flushed, because the
  indexer's peak memory is what the Job's limit has to cover (section 4.5).
"""

from __future__ import annotations

import json
import logging
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .models import Document, Page

log = logging.getLogger("rahbar.indexer.extract")

MIN_TEXT_CHARS = 25          # fewer characters than this on a page = no usable text layer
OCR_DPI = 300
OCR_LANG = "eng"


def _emit(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer.extract", "msg": msg, **fields}), flush=True)


# --------------------------------------------------------------------------- markdown / text
def _strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return text


def _extract_text_file(path: Path, doc_version: str, superseded: bool) -> Document:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".md":
        text = _strip_front_matter(text)
    return Document(path.name, doc_version, superseded, [Page(path.name, 1, text)])


# --------------------------------------------------------------------------- html
class _HtmlText(HTMLParser):
    """Visible text, with headings as Markdown headings and table rows as pipe rows."""

    SKIP = {"script", "style", "noscript", "head", "nav", "footer"}
    BLOCK = {"p", "div", "section", "article", "ul", "ol", "li", "br", "tr", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self._skip = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._heading = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
            self._heading += 1
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.out.append("\n\n")
            self._heading = max(0, self._heading - 1)
        elif tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.out.append("\n| " + " | ".join(self._row) + " |\n")
            self._row = None
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        else:
            self.out.append(data)


def html_to_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html)
    text = "".join(parser.out)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_html(path: Path, doc_version: str, superseded: bool) -> Document:
    html = path.read_text(encoding="utf-8", errors="replace")
    return Document(path.name, doc_version, superseded,
                    [Page(path.name, 1, html_to_text(html))])


# --------------------------------------------------------------------------- pdf
def table_to_pipes(rows: list[list[str | None]]) -> str:
    """Render a pdfplumber table as pipe rows. Cell newlines become spaces."""
    lines = []
    for row in rows:
        cells = [re.sub(r"\s+", " ", (c or "")).strip() for c in row]
        if any(cells):
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _page_text_and_tables(page: Any) -> str:
    """Text of one pdfplumber page with tables re-emitted as pipe rows."""
    try:
        found = page.find_tables()
    except Exception:  # a malformed page must not kill the whole document
        found = []
    tables = [t for t in found if t.extract() and len(t.extract()) >= 2]
    if not tables:
        return str(page.extract_text() or "")
    boxes = [t.bbox for t in tables]

    def outside(obj: dict[str, Any]) -> bool:
        x0, top, x1, bottom = obj["x0"], obj["top"], obj["x1"], obj["bottom"]
        return not any(x0 >= b[0] - 1 and x1 <= b[2] + 1 and top >= b[1] - 1
                       and bottom <= b[3] + 1 for b in boxes)

    text = str(page.filter(outside).extract_text() or "")
    rendered = "\n\n".join(table_to_pipes(t.extract()) for t in tables)
    return f"{text}\n\n{rendered}".strip()


def _ocr_page(path: str, number: int) -> str:
    from pdf2image import convert_from_path
    import pytesseract

    images = convert_from_path(path, dpi=OCR_DPI, first_page=number, last_page=number)
    try:
        return str(pytesseract.image_to_string(images[0], lang=OCR_LANG))
    finally:
        for image in images:
            image.close()


def _extract_pdf(path: Path, doc_version: str, superseded: bool,
                 skip_ocr: bool = False) -> Document:
    import pdfplumber

    pages: list[Page] = []
    ocr_pages = 0
    with pdfplumber.open(str(path)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = _page_text_and_tables(page)
            used_ocr = False
            if len(text.strip()) < MIN_TEXT_CHARS and not skip_ocr:
                try:
                    text = _ocr_page(str(path), number)
                    used_ocr = True
                    ocr_pages += 1
                except Exception as exc:  # tesseract missing, corrupt image, ...
                    _emit("ocr failed", source=path.name, page=number, error=repr(exc))
                    text = ""
            pages.append(Page(path.name, number, text, ocr=used_ocr))
            page.flush_cache()
    empty = sum(1 for p in pages if not p.text.strip())
    _emit("extracted", source=path.name, pages=len(pages), ocr_pages=ocr_pages,
          empty_pages=empty)
    return Document(path.name, doc_version, superseded, pages)


# --------------------------------------------------------------------------- entry point
def extract(path: str, doc_version: str, superseded: bool, skip_ocr: bool = False) -> Document:
    """Return the document's text page by page.

    Detect pages with no text layer and OCR them; those pages are marked ocr=True.
    The OCR libraries need system packages in the Dockerfile (tesseract-ocr,
    poppler-utils), not only pip packages.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(p, doc_version, superseded, skip_ocr=skip_ocr)
    if suffix in {".html", ".htm"}:
        return _extract_html(p, doc_version, superseded)
    if suffix in {".md", ".txt"}:
        return _extract_text_file(p, doc_version, superseded)
    raise ValueError(f"unsupported file type: {p.name}")
