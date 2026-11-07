"""Stage 3: Chunk. Structure-aware, with overlap.

Order of preference when a chunk must be cut: section boundary, then paragraph, then
sentence, then (last resort) a hard word cut. Size and overlap are counted in WORDS
(whitespace tokens); a word is roughly 1.3 model tokens for English.

* Sections come from headings: Markdown "#" headings, numbered headings ("5.4 Academic
  Warning"), and short ALL-CAPS lines. Every chunk starts with its section heading, so the
  embedding sees the heading and the citation can name it.
* Paragraphs are never merged across a section boundary, and overlap never crosses one.
* A table is kept whole when it fits. When it does not, it is split by rows and the header
  row is repeated on every piece, so a column is never separated from its label.
* Failure-injection switch (docs/FAILURE-ANALYSIS.md, stage B): mode="fixed" ignores
  structure and cuts plain fixed-size windows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import Chunk, Document

FRONT_MATTER = "(front matter)"

_MD_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_NUM_HEADING = re.compile(r"^\d+(?:\.\d+){0,3}\.?\s+\S")
_KEYWORD_HEADING = re.compile(r"^(?:chapter|article|section|part|annex|appendix)\s+[\dIVXLC]+\b", re.I)
_CLAUSE = re.compile(r"^(?:\d+(?:\.\d+)+[.)]?|\(\w{1,3}\)|[a-z]\))\s+\S")
_BULLET = re.compile(r"^[-*\u2022\u25cf]\s+\S")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def count_words(text: str) -> int:
    return len(text.split())


@dataclass
class Block:
    section: str
    page: int
    text: str
    is_table: bool = False


def _is_heading(line: str) -> str | None:
    """Return the heading text when `line` is a heading, else None."""
    s = line.strip()
    if not s or s.startswith("|"):
        return None
    m = _MD_HEADING.match(s)
    if m:
        return m.group(1).strip()[:120]
    n = count_words(s)
    if n > 12 or len(s) > 110 or re.search(r"\.{3,}", s):
        return None
    if _NUM_HEADING.match(s) and s[-1] not in ".;,":
        first_alpha = next((c for c in s.split(None, 1)[1] if c.isalpha()), "")
        if first_alpha.isupper():
            return s[:120]
    if _KEYWORD_HEADING.match(s) and s[-1] not in ".;,":
        return s[:120]
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 4 and n <= 10 and all(c.isupper() for c in letters) \
            and s[-1] not in ".;,":
        return s[:120]
    return None


def to_blocks(doc: Document) -> list[Block]:
    """Split a cleaned document into blocks (paragraphs and tables) tagged with the
    section they sit under and the page they start on."""
    blocks: list[Block] = []
    section = FRONT_MATTER
    cur: list[str] = []
    cur_page = 1
    cur_table = False

    def flush() -> None:
        nonlocal cur, cur_table
        if cur:
            text = ("\n" if cur_table else " ").join(cur).strip()
            if text:
                blocks.append(Block(section, cur_page, text, cur_table))
        cur, cur_table = [], False

    for page in doc.pages:
        for raw in page.text.splitlines():
            line = raw.strip()
            if not line:
                flush()
                continue
            if line.startswith("|"):
                if not cur_table:
                    flush()
                    cur_table, cur_page = True, page.page
                cur.append(line)
                continue
            if cur_table:
                flush()
            heading = _is_heading(line)
            if heading is not None:
                flush()
                section = heading
                continue
            if _CLAUSE.match(line) or _BULLET.match(line):
                flush()
            if not cur:
                cur_page = page.page
            cur.append(line)
    flush()
    return blocks


def _split_sentences(text: str, limit: int) -> list[str]:
    """Pieces of at most `limit` words: whole sentences where possible, then words."""
    pieces: list[str] = []
    current: list[str] = []
    used = 0
    for sentence in _SENTENCE_END.split(text):
        n = count_words(sentence)
        if n > limit:                                    # last resort: a hard word cut
            if current:
                pieces.append(" ".join(current))
                current, used = [], 0
            words = sentence.split()
            pieces.extend(" ".join(words[i:i + limit]) for i in range(0, len(words), limit))
            continue
        if used + n > limit and current:
            pieces.append(" ".join(current))
            current, used = [], 0
        current.append(sentence)
        used += n
    if current:
        pieces.append(" ".join(current))
    return pieces


def _split_table(text: str, limit: int) -> list[str]:
    rows = text.splitlines()
    if count_words(text) <= limit or len(rows) < 3:
        return [text]
    header = rows[0]
    pieces: list[str] = []
    current = [header]
    used = count_words(header)
    for row in rows[1:]:
        n = count_words(row)
        if used + n > limit and len(current) > 1:
            pieces.append("\n".join(current))
            current, used = [header], count_words(header)
        current.append(row)
        used += n
    if len(current) > 1:
        pieces.append("\n".join(current))
    return pieces


def _overlap_tail(body: str, overlap: int) -> str:
    """The last ~`overlap` words of `body`, starting at a sentence boundary when possible."""
    if overlap <= 0:
        return ""
    words = body.split()
    if len(words) <= overlap:
        return ""
    tail = " ".join(words[-overlap:])
    parts = _SENTENCE_END.split(tail, maxsplit=1)
    if len(parts) == 2 and count_words(parts[1]) >= max(overlap // 2, 1):
        return parts[1]
    return tail


def _slug(source: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", Path(source).stem.lower()).strip("-")[:60] or "doc"


def _pack_section(section: str, blocks: list[Block], size: int,
                  overlap: int) -> list[tuple[int, str]]:
    """Greedy packing of one section's blocks into chunks. Returns (page, text) pairs."""
    header = section if section != FRONT_MATTER else ""
    budget = max(size - count_words(header), 20)
    limit = max(budget - overlap, 20)       # a unit plus the overlap tail always fits

    units: list[tuple[int, str, bool]] = []
    for b in blocks:
        if count_words(b.text) <= limit:
            units.append((b.page, b.text, b.is_table))
        elif b.is_table:
            units.extend((b.page, piece, True) for piece in _split_table(b.text, limit))
        else:
            units.extend((b.page, piece, False) for piece in _split_sentences(b.text, limit))

    out: list[tuple[int, str]] = []
    cur: list[str] = []
    cur_words = 0
    page = units[0][0] if units else 1
    real = False
    last_was_table = False

    def emit() -> None:
        nonlocal cur, cur_words, real
        if real:
            body = "\n\n".join(cur)
            out.append((page, f"{header}\n\n{body}" if header else body))
        cur, cur_words, real = [], 0, False

    for unit_page, text, is_table in units:
        n = count_words(text)
        if real and cur_words + n > budget:
            previous_body = "\n\n".join(cur)
            emit()
            tail = "" if last_was_table else _overlap_tail(previous_body, overlap)
            if tail:
                cur, cur_words = [tail], count_words(tail)
        if not real:
            page = unit_page
            real = True
        cur.append(text)
        cur_words += n
        last_was_table = is_table
    emit()
    return out


def _chunk_fixed(doc: Document, size: int, overlap: int) -> list[tuple[str, int, str]]:
    """Failure-injection mode: ignore structure, cut fixed windows over the whole text.
    The section label is whatever the window's first word sat under."""
    tagged: list[tuple[str, int, str]] = []
    for b in to_blocks(doc):
        tagged.extend((w, b.page, b.section) for w in b.text.split())
    step = max(size - overlap, 1)
    out = []
    for start in range(0, len(tagged), step):
        window = tagged[start:start + size]
        if not window:
            break
        out.append((window[0][2], window[0][1], " ".join(w for w, _, _ in window)))
    return out


def chunk(doc: Document, size: int, overlap: int, mode: str = "structure") -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` words, with `overlap` words shared between neighbours. Every chunk keeps
    the section heading it sits under, its page, doc_version and superseded."""
    if overlap >= size:
        raise ValueError(f"overlap ({overlap}) must be smaller than size ({size})")
    triples: list[tuple[str, int, str]] = []
    if mode == "fixed":
        triples = _chunk_fixed(doc, size, overlap)
    else:
        by_section: list[tuple[str, list[Block]]] = []
        for b in to_blocks(doc):
            if by_section and by_section[-1][0] == b.section:
                by_section[-1][1].append(b)
            else:
                by_section.append((b.section, [b]))
        for section, blocks in by_section:
            triples.extend((section, p, t) for p, t in _pack_section(section, blocks, size, overlap))
    slug = _slug(doc.source)
    return [
        Chunk(id=f"{slug}-{i:04d}", text=text, source=doc.source, section=section, page=page,
              doc_version=doc.doc_version, superseded=doc.superseded)
        for i, (section, page, text) in enumerate(triples)
    ]
