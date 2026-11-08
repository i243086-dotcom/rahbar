"""Cite only what you retrieved (section 3.4). A citation the retriever never returned is
fabricated, and the case study deducts 10 points for returning one.

reconcile() maps each citation the model produced onto a passage that was really retrieved,
rewrites it to that passage's exact source/section/page, and drops the rest.
"""

from __future__ import annotations

import re

from ..schemas import Citation, Passage


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def section_matches(a: str, b: str) -> bool:
    """Equal, or one is the other's numbered prefix at a clean boundary:
    "5.4" matches "5.4 Academic Warning" but "1.2" does not match "1.21"."""
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if not short or not long_.startswith(short):
        return False
    nxt = long_[len(short)]
    if nxt.isalnum():
        return False
    return not (nxt == "." and long_[len(short) + 1:len(short) + 2].isdigit())


def reconcile(citations: list[Citation], passages: list[Passage]) -> tuple[list[Citation], int]:
    """Returns (valid canonical citations without duplicates, number dropped)."""
    valid: list[Citation] = []
    dropped = 0
    for c in citations:
        matches = [p for p in passages
                   if _norm(p.source) == _norm(c.source) and section_matches(p.section, c.section)]
        if not matches:
            dropped += 1
            continue
        match = next((p for p in matches if p.page == c.page), matches[0])
        canonical = Citation(source=match.source, section=match.section, page=match.page)
        if canonical not in valid:
            valid.append(canonical)
    return valid, dropped
