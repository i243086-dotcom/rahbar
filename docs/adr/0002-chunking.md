# ADR 0002: Structure-aware chunking, measured

## Status
Accepted · 2026-11-08
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
The shipped setting is 400 words with 50 words of overlap. Three settings were measured on the golden set (`docs/PIPELINE.md`, `eval/chunk_experiment_results.txt`).

## Options considered
- **Fixed-size windows.** Simple, and the worst for definitions and clause numbers. It remains as
  `CHUNK_MODE=fixed`, the failure-analysis switch for stage B.
- **Sentence-per-chunk.** Precise but loses context, and the index grows several times larger.
- **Semantic chunking with an embedding model.** Needs the model at chunk time and makes chunk
  boundaries depend on it; not worth it for a corpus with explicit headings.
- **A tokenizer for exact token counts.** Adds a dependency and a model-specific count; words
  are stable and the measurement, not the unit, picks the size.

# Measured result
Three (size, overlap) settings were run through eval/chunk_experiment.py against the 17-question golden set, using nomic-embed-text:

| Size / overlap (words) | Chunks | Amplification | recall@3 | recall@5 |
| --- | --- | --- | --- | --- |
| 200 / 25 | 880 | 1.10 | 0.567 | 0.633 |
| 400 / 50 | 665 | 1.06 | 0.567 | 0.633 |
| 800 / 100 | 584 | 1.04 | 0.567 | 0.633 |

Recall was identical for all three. Most clauses in this corpus are shorter than 200 words, so the structure-aware chunker keeps them whole whichever limit is set, and the golden set scores sections, not chunk boundaries. Size therefore did not decide the result. 400 / 50 was chosen on the other criteria: 200 / 25 stores about 32% more chunks (more embedding time and storage) for no gain, and 800 / 100 allows long chunks in which one clause is a small part of a much larger section, which is a risk for exact-term questions. The experiment ranks superseded documents out, as the API does by default, so the version score understates the live system.  

## Consequences
Citations can name a real section. Overlap costs storage (amplification is reported). A document
without recognisable headings falls back to paragraph and sentence splitting under one section,
so its citations are coarse. Re-measure whenever the corpus changes materially, using
`eval/chunk_experiment.py`; the CI gate catches a regression in recall@5 afterwards.
