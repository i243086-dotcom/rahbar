# Indexing and retrieval pipeline

> Cells and sentences marked **FILL-IN** need a number you measure yourself; the design text
> around them is written. Search for `FILL-IN` before submitting. Every number must come from a run.

Indexing runs once, and again when the material changes. Querying runs on every question.
That is why the indexer is a Job (`docs/adr/0001-indexer-as-job.md`) and the API only reads.
How the documents reach the Job: a volume. The indexer image is built from `indexer/`, so `corpus/` is not inside it and the PDFs are not committed either; `corpus/raw` (including `_index.json`) is copied into a PVC (`corpus-data`) that the Job mounts read-only, so re-indexing needs no image rebuild.

## Extraction
`indexer/pipeline/extract.py`. PDFs are read page by page with pdfplumber. A page whose text layer
has fewer than 25 characters is rasterised at 300 dpi and OCR'd with Tesseract, and marked
`ocr=True`. Tables found by pdfplumber are cut out of the running text and re-emitted as
pipe-separated rows, so a column stays attached to its label. HTML pages keep `<table>` rows as pipe
rows; Markdown is read as is. One bad document is logged and skipped, not fatal.

* **Documents that needed OCR:** 41 pages in total: 24 of 26 pages of the 2023 Undergraduate Academic Rules, 8 of 8 pages of the Faculty Start-ups Policy, 5 pages of the 2026 Academic Rules Handbook and 4 pages of the Student Handbook. Nothing was skipped (dry run: 665 chunks from 9 documents).
* **Before and after for a table:** FILL-IN. Paste the raw `pdftotext` output of one table beside the pipe rows the indexer produced (see `python -m pipeline.run --dry-run --dump`).
* **What could not be recovered:**
  1. Two-column pages 8-11 of the 2026 handbook are interleaved: chunk `academic-rules-handbook-jun-2026-0031` mixes clause 1.20 with text of 1.8 and 1.9, and `-0046` interleaves 1.22 with an SGPA/CGPA paragraph. Clean copies of those clauses survive (`-0039` is 1.21, `-0040` is 1.22).
  2. 2023 OCR: the table of contents is garbled, chunk `-0022` (GPA calculation 2.4-2.11) kept the clause numbers but lost their text, and the 2023 attendance clause 1.21 is split across chunks `-0012` and `-0013`.
  3. Scanned policy: OCR junk at the start of some chunks and wrong section labels (every page-2 chunk is labelled `1. Purpose`). Some Student Handbook chunks also carry wrong section labels.

## Cleaning
`indexer/pipeline/clean.py`. Rules: normalise unicode (NFKC, ligatures, non-breaking spaces, control
characters); drop lines that repeat at the top or bottom of at least 40% of pages (running headers
and footers) after masking digits; drop bare page numbers; drop table-of-contents lines with dot
leaders; re-join words hyphenated across a line break; collapse blank lines.

* **Deliberately not stripped:** clause and section numbers (`1.21`, `5.4`), headings, table rows,
  and instruction-like sentences. Numbering is what citations and exact-term queries depend on, and
  injected text is handled on the query side (`api/app/services/guard.py`) where it is visible in logs,
  rather than silently deleted from the index. A unit test pins this down
  (`indexer/tests/test_extract_clean.py`). The first version of the header rule wrongly removed
  numbered headings because masking digits made "1. Section 1" and "2. Section 2" look identical;
  numbered lines are now exempt.

## Chunking
`indexer/pipeline/chunk.py`, ADR `docs/adr/0002-chunking.md`. Unit: words. Order of preference:
section, paragraph, sentence, hard cut. Overlap stays inside a section. Each chunk starts with its
heading.

Shipped: size **400** words, overlap **50** words. Storage amplification (stored words / original words)
is printed by the indexer as `storage_amplification`: **1.059** (91,840 stored / 86,708 original words; the lecture's example was 150 / 120 = 1.25).

Measured with `python eval/chunk_experiment.py --corpus corpus/raw --golden eval/golden.yaml --configs 200:25,400:50,800:100`
against the golden set, same embedding model, superseded documents excluded:

| Size (words) | Overlap (words) | recall@3 | recall@5 | Chunks stored | Amplification |
| --- | --- | --- | --- | --- | --- |
| 200 | 25 | 0.567 | 0.633 | 880 | 1.10 |
| 400 | 50 | 0.567 | 0.633 | 665 | 1.06 |
| 800 | 100 | 0.567 | 0.633 | 584 | 1.04 |

Why the shipped one: recall was identical for all three configurations (0.567 at 3, 0.633 at 5), so recall did not decide it. The chunker is structure-aware, so most clauses (under 200 words) are never cut whatever the target size, and the golden set scores (source, section) pairs rather than chunk boundaries. We shipped 400/50 on cost and risk: 200/25 stores 880 chunks (about 32% more than 665) for no gain, and 800/100 allows long chunks in which one clause is a small part of a large section. The experiment is vector search only and always excludes superseded documents, so its exact-term score (0.33) and version score (0.5) understate the live system.

## Embedding
Model `nomic-embed-text` (768 dimensions) through Ollama's `/api/embed`, batched 16 at a time.
Documents are embedded with the prefix `search_document: ` and questions with `search_query: `, as
the model was trained. The pin is the `EMBED_MODEL` key of one ConfigMap, read by both the indexer
and the API. On top of that the indexer writes `embed_model` and `dimension` into the collection
metadata (`indexer/pipeline/store.py:38-39`), and the API compares them with its own value in
`api/app/services/readiness.py:15` on every readiness probe. A mismatch keeps the pod at `0/1` and
logs which models conflict. The indexer builds into `rahbar__build` and renames it over `rahbar`
only when every chunk is written, so a failed Job leaves the old index serving.

Metadata schema (every chunk): `source`, `section`, `page`, `doc_version`, `superseded`.
Chunk count: **665** (768-dimension vectors, model `nomic-embed-text`).

## Retrieval
`api/app/retrieval/chroma.py`. The question is embedded once (the vector is reused for the cache
lookup and the search). Chroma is queried for the top `FETCH_K` (20) with the filter
`superseded = false`, unless the question explicitly asks about an older version, by wording ("the old
rules") or by naming a year that belongs to a superseded document ("in 2023"). That is what stops the
retriever quoting a repealed clause (failure mode E): metadata filtering fixes it, a prompt does not.
Exact terms (clause numbers, course codes, amounts, percentages) found in the question are also
searched literally with `where_document $contains`; chunks containing them get a boost and up to
`k // 2` reserved slots, because a boost alone cannot rescue a chunk whose vector is far from the question.

## Honest abstention
If no retrieved chunk has similarity >= `RELEVANCE_FLOOR`, and none contains the question's exact
term, the API returns `answered_from_context: false` without calling the model. The floor is chosen
from `min_top1_score_answerable` and `max_top1_score_must_abstain` in `eval/results.json`: it belongs
between them. Shipped value: **0.63**, from `max_top1_score_must_abstain` = 0.6235 (the hostel questions) and `min_top1_score_answerable` = 0.6364. The gap is only 0.013, so the floor is a safety net, not the main mechanism: the exact-term bypass keeps clause questions answerable, and the model's own "not in the documents" answer is the second layer.

## Semantic cache
`api/app/services/cache.py`, ADR `docs/adr/0003-cache-store.md`. A hit is cosine similarity >=
`CACHE_THRESHOLD`, for the same scope and index build. Chosen with `python eval/cache_threshold.py`
(lowest threshold with zero false hits):

| Threshold | Paraphrases missed | False hits |
| --- | --- | --- |
| FILL-IN | FILL-IN | FILL-IN |
| FILL-IN | FILL-IN | FILL-IN |
| FILL-IN | FILL-IN | FILL-IN |

The false hit that ruled a lower threshold out: FILL-IN (the pair of questions and their similarity).
Shipped: **FILL-IN**. Never cached: follow-ups, abstentions, fallbacks, answers with a dropped citation.
Invalidated on re-index by the indexer (`indexer/pipeline/cache.py`) and, as a second layer, by the
`index_id` check on every lookup.

## Evaluation method
`eval/run_eval.py`. recall@k compares the golden `(source, section)` pairs with the `retrieved` list
in the API response: sources match case-insensitively, sections match when equal or when one is the
other's numbered prefix at a clean boundary (`5.4` matches `5.4 Academic Warning`, `1.2` does not match
`1.21`). Several chunks from one section count once. Citation validity is the fraction of returned
citations that match a retrieved chunk; the API also reports `citations_dropped`, the fabricated
citations it removed before answering, so the metric cannot look perfect only because the API cleaned up.
Abstention correctness must be 100%. `injection_resisted` is reported, not gated.
