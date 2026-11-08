# Failure analysis

> Break four of the six stages on purpose, one at a time, restore each, and record what you
> **observed**. The "Expected" lines are hypotheses to test, not results; replace them with what
> actually happened (copy the log line or metric you saw). Each switch below is a ConfigMap key
> that is healthy by default, so breaking a stage is one `kubectl edit configmap` plus a
> restart (or a re-index for A and B), and restoring it is the reverse. Re-run
> `python eval/run_eval.py` after each one and keep the numbers.

| Stage | How to break it | Switch |
| --- | --- | --- |
| A Extraction | Index the scanned PDF without OCR | `SKIP_OCR=true` on the indexer, then re-index |
| B Chunking | Fixed 100-word windows, no overlap | `CHUNK_MODE=fixed CHUNK_SIZE=100 CHUNK_OVERLAP=0`, then re-index |
| C Retrieval | `TOP_K=1`, or change `EMBED_MODEL` on the API only | ConfigMap, restart the API |
| D Prompt | Remove "use only the supplied context" | `PROMPT_GROUNDING=false`, restart the API |
| E Source | Remove the superseded filter, ask a version-sensitive question | `INCLUDE_SUPERSEDED=true`, restart the API |
| F Generation | Temperature 1.2 | `TEMPERATURE=1.2`, restart the API |

## Stage ? · name (FILL-IN, copy this block four times)
- **What we broke:** FILL-IN
- **Symptom:** FILL-IN (the question asked, the wrong behaviour, and the eval numbers before and after)
- **Diagnosis, as if we had not caused it:** FILL-IN (which log line, metric or command shows it)
- **Remedy:** FILL-IN

## Where to look, per stage (use this to write the diagnosis)
These are the places the evidence lives; confirm each against what you saw.

- **A:** the indexer's `extracted` log line shows `ocr_pages` and `empty_pages` per document; a scanned
  document with `empty_pages` equal to its page count was indexed as nothing. Questions about it
  abstain, and recall for them is 0. `inspect_corpus.py` flags it before indexing at all.
- **B:** the `chunking summary` log line shows `storage_amplification` and `chunks`; recall@5 by type
  falls, and `exact` and definition questions fall first. Retrieved sections look right but the chunk
  starts or ends mid-clause.
- **C:** the per-request log line carries `chunk_ids` and `scores`; with `TOP_K=1` the right section is
  absent whenever it was second. With a changed `EMBED_MODEL` the pod never becomes ready
  (`/readyz` returns 503 naming `embedding_pin`), which is the guardrail working; to see the silent
  version, disable it first and watch the scores collapse to noise.
- **D:** the retrieved chunks and scores are fine but the answer contains facts that are in no chunk;
  `citation_validity` or `citations_dropped_by_api` rises, and a must-abstain question may be answered.
- **E:** the log line shows a retrieved chunk with the older `doc_version`; the answer quotes a
  repealed number. `scope` in the log line reads `all` when it should read `current`.
- **F:** the retrieved context is unchanged; only the answer varies run to run. `rahbar_fallbacks_total`
  rises as JSON validity drops. Only F is the model's fault, so check A to E first.
