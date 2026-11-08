#!/usr/bin/env python3
"""Measure the corpus against the seven required properties (section 2) and print a table for
docs/CORPUS.md.   python corpus/inspect_corpus.py [corpus/raw]

Per document: pages, pages with no text layer (the scan test; the same idea as `pdffonts`
printing an empty list), tables found, words, doc_version and superseded from _index.json.
Totals are checked against property 1 (6 documents, 40 pages).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def inspect_pdf(path: Path) -> tuple[int, int, int, int]:
    import pdfplumber

    pages = no_text = tables = words = 0
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            pages += 1
            text = page.extract_text() or ""
            if len(text.strip()) < 25:
                no_text += 1
            words += len(text.split())
            try:
                tables += sum(1 for t in page.find_tables() if len(t.extract() or []) >= 2)
            except Exception:  # noqa: BLE001
                pass
            page.flush_cache()
    return pages, no_text, tables, words


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "raw")
    index_file = root / "_index.json"
    meta = {e["file"]: e for e in json.loads(index_file.read_text())} if index_file.exists() else {}
    rows, total_pages = [], 0
    for path in sorted(root.glob("*")):
        if path.name.startswith("_") or path.suffix.lower() not in {".pdf", ".html", ".md", ".txt"}:
            continue
        m = meta.get(path.name, {})
        if path.suffix.lower() == ".pdf":
            pages, no_text, tables, words = inspect_pdf(path)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            pages, no_text, tables, words = 1, 0, text.lower().count("<table"), len(text.split())
        total_pages += pages
        flag = "SCANNED (needs OCR)" if no_text and no_text >= pages * 0.8 else (
            f"{no_text} pages without text" if no_text else "")
        rows.append((path.name, m.get("doc_version", "?"), m.get("superseded", "?"),
                     pages, tables, words, flag))
    print("| File | doc_version | superseded | Pages | Tables | Words | Notes |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    print(f"\nDocuments: {len(rows)} (need >= 6)   Pages: {total_pages} (need >= 40)")
    print("Scanned documents:", [r[0] for r in rows if r[6].startswith("SCANNED")] or "none found")
    print("Versions pair:", sorted({(r[1], r[2]) for r in rows}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
