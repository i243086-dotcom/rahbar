# AI usage

Each of us documents our own use in our own section. A specific disclosure carries no penalty.

## Student A (data and intelligence)

| Tool | What it wrote or shaped | What we changed afterwards, and why |
| --- | --- | --- |
| Claude (Anthropic), via claude.ai | First drafts of: `indexer/pipeline/{extract,clean,chunk,embed,store,cache}.py` and their tests; `api/app/retrieval/*`, `api/app/services/{answer,cache,citations,guard,policy,prompt,readiness}.py`, `api/app/providers/llm/*`; `eval/run_eval.py` metrics and gate, `eval/chunk_experiment.py`, `eval/cache_threshold.py`, `eval/validate_golden.py`, `corpus/inspect_corpus.py`; a draft golden set with unfilled `relevant` fields; the structure of `docs/CONTRACT.md`, ADRs 0002 to 0004, and the prose scaffolding of `docs/PIPELINE.md`, `CORPUS.md`, `FAILURE-ANALYSIS.md` | FILL-IN: for each file, what you read, ran and changed. Examples to check and replace with the truth: golden questions rewritten against the real PDFs; `RELEVANCE_FLOOR`, `CACHE_THRESHOLD`, chunk size and overlap set from our own measurements; ADR wording edited into our own words; the cleaner's header rule and the exact-term slot reservation were bugs the tests found in the first drafts, and we should be able to explain both |

Everything marked FILL-IN in the docs was left for us on purpose, because it must come from a run
on our own machine. We can explain every module above line by line.

## Student B (platform and DevOps)
OpenAI Codex adapted the Docker images, Kubernetes overlays, workflow and deployment scripts to the shared contract. It also drafted platform documentation and ran local verification. Student B should append the changes and verification they personally performed, with their reasons.
