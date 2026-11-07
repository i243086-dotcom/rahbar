# ADR 0002: Structure-aware chunking, measured

## Status
Accepted · 2026-11-07 (the shipped size and overlap are filled in after the experiment)

## Context
Chunking decides what the retriever can find. A chunk cut in the middle of a definition loses its
subject; a chunk that is too large blurs several topics into one vector. The corpus has numbered
clauses, definitions, tables and a scanned policy, so a fixed window is the likely wrong default.

## Decision
Chunk by structure, in this order of preference: section boundary, paragraph, sentence, and only
then a hard word cut. Size and overlap are counted in words (whitespace tokens, roughly 1.3 model
tokens each). Overlap is shared between neighbours inside a section and never crosses a section.
Every chunk begins with its section heading, so the embedding sees it and the citation can name it.
A table is kept whole when it fits; otherwise it is split by rows and the header row is repeated.
The shipped (size, overlap) is the best of three measured settings (`docs/PIPELINE.md`):
**SIZE_FILL / OVERLAP_FILL**.

## Options considered
- **Fixed-size windows.** Simple, and the worst for definitions and clause numbers. It remains as
  `CHUNK_MODE=fixed`, the failure-analysis switch for stage B.
- **Sentence-per-chunk.** Precise but loses context, and the index grows several times larger.
- **Semantic chunking with an embedding model.** Needs the model at chunk time and makes chunk
  boundaries depend on it; not worth it for a corpus with explicit headings.
- **A tokenizer for exact token counts.** Adds a dependency and a model-specific count; words
  are stable and the measurement, not the unit, picks the size.

## Consequences
Citations can name a real section. Overlap costs storage (amplification is reported). A document
without recognisable headings falls back to paragraph and sentence splitting under one section,
so its citations are coarse. Re-measure whenever the corpus changes materially, using
`eval/chunk_experiment.py`; the CI gate catches a regression in recall@5 afterwards.
