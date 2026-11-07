"""Exact-term handling: the part of hybrid retrieval that embeddings cannot do.

Embeddings blur exact strings: "clause 1.21", "CS-1002" and "10,000" all land near any
passage about the same topic. So the retriever pulls the exact terms out of the question,
asks Chroma for chunks that literally contain them (where_document $contains), merges those
with the vector hits, and gives a chunk that contains the term a small score boost.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\b\d+(?:\.\d+)+\b"),                   # clause numbers and decimals: 1.21, 2.00
    re.compile(r"\b[A-Za-z]{2,4}[- ]?\d{3,4}\b"),       # course codes: CS-1002, MT 1003
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b"),              # amounts: 10,000
    re.compile(r"\b\d+(?:\.\d+)?\s?%"),                 # percentages: 80%
]
MAX_TERMS = 3


def exact_terms(question: str) -> list[str]:
    """Up to MAX_TERMS distinct exact terms, most specific first."""
    seen: list[str] = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(question):
            term = m.group(0).strip()
            if term not in seen:
                seen.append(term)
    return seen[:MAX_TERMS]


def contains_term(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)
