# Corpus

Source: FAST-NUCES public website (nu.edu.pk), public pages only. The PDFs are not committed:
`corpus/MANIFEST.md` holds each URL and SHA-256 and `corpus/fetch.py` re-downloads them
(`make fetch`, then `python corpus/fetch.py --verify`, which printed "9 of 9 match the manifest").
Documents: **9** · Pages: **281** (from `python corpus/inspect_corpus.py`)

| File | doc_version | superseded | Pages | Tables | Words |
| --- | --- | --- | --- | --- | --- |
| academic-rules-handbook-jun-2026.pdf | 2026-06 | false | 58 | 60 | 14622 |
| annual-report-2019-20.pdf | 2019-20 | false | 33 | 27 | 7201 |
| annual-report-2023-24.pdf | 2023-24 | false | 85 | 43 | 29210 |
| faculty-entrepreneurship-and-technical-start-ups-policy.pdf | 2022-05 | false | 8 | 0 | 0 (scanned) |
| fee-structure-page.html | 2026-27 | false | 1 | 3 | 3499 |
| grading-page.html | 2026 | false | 1 | 5 | 3696 |
| prospectus-2026-academic-rules-and-regulations.pdf | 2026 | false | 5 | 5 | 3497 |
| student-handbook-jun-2026.pdf | 2026-06 | false | 64 | 69 | 21424 |
| undergraduate-academic-rules-aug-2023.pdf | 2023-08 | true | 26 | 0 | 21 (24 pages scanned) |

| # | Required property | Document(s) that provide it | Evidence or notes |
| --- | --- | --- | --- |
| 1 | At least 6 documents, 40 pages | The table above | Totals: 9 documents, 281 pages |
| 2 | Two versions of one policy | Undergraduate Academic Rules (Aug 2023, `superseded: true`) and Academic Rules Handbook (Jun 2026, current) | `doc_version` and `superseded` come from `corpus/sources.yaml` into `_index.json` into chunk metadata. Honest note: the two versions are mostly word for word identical (clauses 1.22, 5.4, 5.5, 5.6 match, and both contain the 100% attendance rule with 20% condonation). The clean difference we found is the minimum CGPA for graduation: clause 1.26 in 2023, clause 1.25 in 2026. The 2026 handbook also adds the Generative AI policy and S/U grades. A `difflib` comparison by clause number showed most other differences were two-column layout noise. |
| 3 | Scanned, image-only PDF | Faculty Entrepreneurship and Technical Start-ups Policy | `pdffonts` prints an empty font list, so it has no text layer; all 8 of its 8 pages were OCR'd. The 2023 rules are mixed: `pdffonts` shows embedded fonts (Calibri, Calibri-Bold, LEMONMILK) because the cover has real text, but 24 of its 26 pages were OCR'd. |
| 4 | A table with real information | Fee Structure and Grading pages (HTML tables); Annual Reports; both handbooks | Tables found: handbook 2026 60, annual report 2023-24 43, annual report 2019-20 27, student handbook 69, fee page 3, grading page 5, prospectus 5 |
| 5 | Long definitions | Student Handbook (Generative AI policy with numbered sub-sections) and the 2026 Academic Rules Handbook (Generative AI policy, pp 40-54) | Section 5 of the Generative AI policy ("Unacceptable Uses of Generative AI Tools") in the 2026 handbook is stored as three consecutive chunks of 399, 393 and 395 words (`academic-rules-handbook-jun-2026-0168` to `-0170`): over 1,100 words of connected sub-clauses that a 200-word fixed window would cut into at least six pieces, separating sub-clauses from their heading |
| 6 | A deliberately absent topic | Hostel rules (the Prospectus "Transport and Hostel Facilities" PDF is left out) | A new student plausibly asks about visitors, curfew and fees. We checked the indexed chunks: "hostel" appears only in passing in 8 chunks, with no visitor or curfew rules, no hostel fees and no mess menu. |
| 7 | Exact-term content | Clause numbers (attendance 1.21, warning 5.4), CGPA thresholds, fees per credit hour (Rs. 12,000), Applicant Admission Fee (Rs. 3,000) | The Prospectus uses different clause numbers for the same rules, which is itself a trap |

Traps found while choosing (also in the case study): the Prospectus 2025 vs 2026 naming mismatch,
the Academic Calendar's 2023-24 holidays table beside the 2026-27 schedule.
