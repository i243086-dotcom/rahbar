# What the platform side needs from the data side (and what changed in the shared files)

## Images
- **indexer image** (`indexer/`): apt packages `tesseract-ocr` and `poppler-utils`, then `pip install -r requirements.txt`. Entry: `python -m pipeline.run`. Needs the documents at `CORPUS_DIR` (decide: baked in, init container, or volume; write it in `docs/PIPELINE.md`). Run as non-root with a read-only root filesystem: mount an `emptyDir` at `/tmp` (pdf2image and Tesseract write temporary files there).
- **api image** (`api/`): `pip install -r requirements.txt`, start with `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Dev-only packages (`reportlab`, `fakeredis`, pytest, ruff, mypy) are in `requirements-dev.txt`, not in the images.

## ConfigMap and Secret
See `docs/CONTRACT.md` for every key. The ones that are easy to forget: `REDIS_HOST` and `REDIS_PORT` on the **indexer** too (it expires the cache), `CACHE_ENABLED=true` on the API, `RETRIEVER=chroma`, `LLM_NUM_CTX=8192`. `EMBED_MODEL` must come from one key for both.

## NetworkPolicy
The indexer needs egress to: chroma:8000, redis:6379, DNS, and Ollama on the host (`host.minikube.internal`). The API needs egress to chroma, redis, DNS and Ollama (embeddings are always through Ollama, even with a hosted LLM).

## Probes and resources
- `/healthz` is dependency-free; `/readyz` is implemented in `api/app/services/readiness.py` and returns 503 with `failed` naming the dependency. Do not rewrite it, but own the probe settings.
- Indexer memory: set the limit from `kubectl top pods` while the Job runs on the real corpus. OCR at 300 dpi is the peak. Exit code 137 means the limit is too low.
- The Job's exit code: 0 = index written; 1 = failure (Kubernetes retries up to `backoffLimit`); 2 = a stage not implemented (cannot happen now).

## Changes I made in files that overlap with yours
`api/app/main.py` (lifespan: builds the cache, runs a startup readiness check), `api/app/routes/health.py` (`/readyz`), `api/app/routes/metrics.py` (new query-pipeline metrics, the starter's two are unchanged), `api/app/routes/ask.py` (passes the cache, sets `X-Cache`). Keep `api/app/schemas.py` additions: `cached`, `citations_dropped`, and three optional `Passage` fields.

## Demonstrations that depend on my side
- Re-index without redeploy: `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar`.
- Embedding-pin demo: change `EMBED_MODEL` in the ConfigMap, restart only the API, show `0/1 READY` and the log line `not ready` with `dependency: embedding_pin`.
- First real-pipeline run: `RETRIEVER=chroma`, `LLM_PROVIDER=ollama-host`, run the Job, check `kubectl logs job/...` for the `chunking summary` line.
