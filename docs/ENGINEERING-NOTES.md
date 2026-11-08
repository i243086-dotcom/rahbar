# Engineering notes

<!-- STARTER-TODO(7): answer all seven questions from section 7 of the case study, each
     pointing to your own files and line numbers. A generic answer scores zero. -->

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong

## 5. recall@5 by question type: where is it worst, and why?

*(Student A. The reasoning is written; the numbers must be yours.)*

From `eval/results.json`, `recall_at_5_by_type`: ordinary FILL-IN, version FILL-IN, exact FILL-IN,
injection FILL-IN. Worst: FILL-IN (expected to be `exact`; if it is not, say what you found instead,
because that is the finding).

Why embeddings struggle with exact terms: an embedding places text by meaning, so "clause 1.21",
"clause 1.2" and "clause 5.4" all land near any passage about the same topic, and a number carries
almost no meaning to the model. The right chunk may exist and still rank below five other attendance
passages. The technique from the RAG lecture that addresses it is hybrid retrieval: combine the
vector search with a literal match. Ours is `api/app/retrieval/exact.py` (extracts clause numbers,
course codes, amounts and percentages from the question) and `api/app/retrieval/chroma.py:88-125`
(a second query with `where_document $contains`, a score boost, and `k // 2` reserved slots, because a
boost alone cannot rescue a chunk whose vector is far from the question: the unit test
`api/tests/test_retrieval.py::test_exact_term_search_rescues_a_chunk_the_vectors_ranked_low`
failed on the first version for exactly that reason). Effect measured: exact recall@5 FILL-IN
without it (`EXACT_BOOST=0` and no `$contains`), FILL-IN with it.

## 6. EMBED_MODEL changed on the API only: what does your system do?

*(Indexer and API halves are mine; Student B adds the cluster demonstration and the
`kubectl get pods` / log screenshots.)*

The indexer records the model it used in the collection metadata, `indexer/pipeline/store.py:38-39`
(`embed_model` and `dimension`). On every readiness probe the API reads that metadata and compares it
with its own `EMBED_MODEL` in `api/app/services/readiness.py:15-26` (`pin_mismatch`). On a mismatch
`/readyz` returns 503 with `failed: embedding_pin` and a message naming both models, the log carries
one `not ready` line with the same text, and the pod stays at `0/1 READY`, so the Service never sends
it a question. The already-running pods built with the old value keep serving until they restart,
which is the correct behaviour during a rolling update: new pods wait, old pods serve.

Without the guardrail: the API would embed questions with the new model and search vectors built
by the old one. The dimensions may differ (Chroma then raises an error and every question falls back),
but with two 768-dimension models there is no error at all. Cosine similarity between unrelated spaces is
noise, so retrieval returns arbitrary chunks with plausible-looking scores, the relevance floor lets
some of them through, and the model confidently answers from the wrong passages. Nothing is logged as
an error. That is the silent failure the pin exists to make unreachable.

## 7. The failure that cost us more than an hour
