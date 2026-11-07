"""Stage 2: Clean. Remove artefacts without destroying structure.

Rules (also listed in docs/PIPELINE.md):
  1. Normalise unicode spaces, ligatures and control characters.
  2. Drop lines that repeat on many pages (running headers and footers), never numbered
     headings or clauses. A line is
     "repeating" when, with digits replaced by '#', it opens or closes at least
     REPEAT_FRACTION of the pages. Only the first and last few lines of a page are tested,
     so a genuine sentence in the middle of a page is never removed.
  3. Drop bare page numbers ("12", "Page 12 of 53", "- 12 -").
  4. Re-join words hyphenated across a line break ("exami-\\nnation").
  5. Drop table-of-contents lines with dot leaders ("5.4 Academic Warning ........ 12"): they
     repeat every heading's words and would out-rank the real section in retrieval.
  6. Collapse runs of blank lines and trailing spaces.

Deliberately NOT stripped: clause and section numbers ("1.21", "5.4"), headings,
pipe-table rows, and any sentence that looks like an instruction. The retriever
and the citations need the numbering; instruction-like text is a security question for
the query side (api/app/services/guard.py), not something to silently delete from the
index where nobody can see it.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .models import Document, Page

EDGE_LINES = 3             # how many lines at the top / bottom of a page are header/footer candidates
REPEAT_FRACTION = 0.4      # a candidate seen on this fraction of pages is a header or footer
MIN_PAGES_FOR_REPEAT = 4   # with fewer pages there is no reliable "repeats on every page"

_PAGE_NUMBER = re.compile(
    r"^\s*(?:[-–—]\s*)?(?:page\s+)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?(?:\s*[-–—])?\s*$", re.I)
_TOC_LINE = re.compile(r"\.{4,}\s*\d{1,4}\s*$|(?:\.\s){4,}\d{1,4}\s*$")
_LIGATURES = {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl"}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _normalise_chars(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    return _CONTROL.sub("", text)


_NUMBERED = re.compile(r"^\s*\d+(?:\.\d+)+\.?\s+\S|^\s*\d+\.\s+[A-Za-z]")


def _is_numbered(line: str) -> bool:
    """Clause and heading numbers ("5.4 Warning", "3. Fees") are content, never a running header,
    even if masking their digits makes them look identical from page to page."""
    return bool(_NUMBERED.match(line))


def _shape(line: str) -> str:
    """The line with digits masked, so 'Page 3' and 'Page 4' count as the same footer."""
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def _repeating_shapes(pages: list[Page]) -> set[str]:
    if len(pages) < MIN_PAGES_FOR_REPEAT:
        return set()
    seen: Counter[str] = Counter()
    for page in pages:
        lines = [ln for ln in page.text.splitlines() if ln.strip()]
        edge = lines[:EDGE_LINES] + lines[-EDGE_LINES:]
        for shape in {_shape(ln) for ln in edge if not _is_numbered(ln)}:
            if shape and len(shape) > 2:
                seen[shape] += 1
    need = max(2, int(len(pages) * REPEAT_FRACTION))
    return {shape for shape, n in seen.items() if n >= need}


def _clean_page(text: str, repeating: set[str]) -> str:
    out: list[str] = []
    lines = text.splitlines()
    non_empty = [i for i, ln in enumerate(lines) if ln.strip()]
    edge = set(non_empty[:EDGE_LINES]) | set(non_empty[-EDGE_LINES:])
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if i in edge and not _is_numbered(stripped) and _shape(stripped) in repeating:
            continue
        if _PAGE_NUMBER.match(stripped) and i in edge:
            continue
        if _TOC_LINE.search(stripped):
            continue
        out.append(stripped)
    joined = "\n".join(out)
    joined = re.sub(r"(\w)-\n(\w)", r"\1\2", joined)          # exami-\nnation
    joined = re.sub(r"[ \t]{2,}", " ", joined)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them."""
    normalised = [Page(p.source, p.page, _normalise_chars(p.text), p.ocr) for p in doc.pages]
    repeating = _repeating_shapes(normalised)
    pages = [Page(p.source, p.page, _clean_page(p.text, repeating), p.ocr) for p in normalised]
    return Document(doc.source, doc.doc_version, doc.superseded, pages)
