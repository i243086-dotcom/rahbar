# Corpus

> **FILL-IN** marks what you must measure after `make fetch` and
> `python corpus/inspect_corpus.py`. The "Document(s)" column is pre-filled from the starter's
> candidate list; confirm each file still downloads and is what its name says.

Source: FAST-NUCES public website (nu.edu.pk), public pages only. The PDFs are not committed:
`corpus/MANIFEST.md` holds each URL and SHA-256 and `corpus/fetch.py` re-downloads them
(`make fetch`, then `python corpus/fetch.py --verify`). Documents: **FILL-IN** · Pages: **FILL-IN**

| # | Required property | Document(s) that provide it | Evidence or notes |
| --- | --- | --- | --- |
| 1 | At least 6 documents, 40 pages | See the table from `inspect_corpus.py` | Totals: FILL-IN documents, FILL-IN pages |
| 2 | Two versions of one policy | Undergraduate Academic Rules (Aug 2023, `superseded: true`) and Academic Rules Handbook (Jun 2026, current) | `doc_version` and `superseded` come from `corpus/sources.yaml` into `_index.json` into chunk metadata. If the 2023 file does not download, choose another real pair (Annual Reports, EE PLOs) and say so here |
| 3 | Scanned, image-only PDF | Faculty Entrepreneurship and Technical Start-ups Policy | FILL-IN: paste `pdffonts` output (empty list = scan) and the indexer's `ocr_pages` log line |
| 4 | A table with real information | Fee Structure and Grading pages (HTML tables); Annual Reports | FILL-IN: tables found per document from `inspect_corpus.py` |
| 5 | Long definitions | Student Handbook (Generative AI policy with numbered sub-sections) | FILL-IN: name one definition that a 200-word fixed window would cut |
| 6 | A deliberately absent topic | Hostel and transport rules (the Prospectus "Transport and Hostel Facilities" PDF is left out) | FILL-IN: why a student plausibly asks (a new student always does). Confirm no kept document answers it |
| 7 | Exact-term content | Clause numbers (attendance 1.21, warning 5.4), CGPA thresholds, fees per credit hour | The Prospectus uses different clause numbers for the same rules, which is itself a trap |

Traps found while choosing (also in the case study): the Prospectus 2025 vs 2026 naming mismatch,
the Academic Calendar's 2023-24 holidays table beside the 2026-27 schedule. FILL-IN anything you found yourself.
