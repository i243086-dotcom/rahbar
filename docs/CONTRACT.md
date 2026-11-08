# Contract between the data/intelligence side and the platform side

Agreed before either of us started, so each side can work and test alone. If one of these
changes, change this file in the same pull request and tell the other person.

## Chroma
| Item | Value |
| --- | --- |
| Collection | `rahbar` (`CHROMA_COLLECTION`). The indexer builds `rahbar__build`, then renames it over `rahbar` |
| Distance | cosine (`hnsw:space`). The API converts distance to similarity: `1 - distance` |
| Chunk metadata | `source` str, `section` str, `page` int, `doc_version` str, `superseded` bool |
| Collection metadata | `embed_model`, `dimension`, `index_id`, `built_at`, `chunk_size`, `chunk_overlap`, `chunk_count`, `superseded_versions` |
| Server / client | `chromadb/chroma:1.0.12` / `chromadb-client==1.0.12` |
| Writer | the indexer Job only. The API never writes to Chroma |

## Redis (semantic cache)
Keys all start with `rahbar:cache:`. The indexer deletes every key with that prefix after a
re-index. The API also tags entries with `index_id` and ignores entries from another index.

## Ports and service names
`api:8000`, `ui:8080` (Service port 80), `chroma:8000`, `redis:6379`.

## ConfigMap keys (read by api and indexer unless noted)
| Key | Read by | Shipped value | Meaning |
| --- | --- | --- | --- |
| `EMBED_MODEL` | api, indexer | `nomic-embed-text` | THE PIN. One key, two readers |
| `OLLAMA_URL` | api, indexer | `http://host.minikube.internal:11434` | Embeddings always go through Ollama |
| `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION` | api, indexer | `chroma`, `8000`, `rahbar` | |
| `REDIS_HOST`, `REDIS_PORT` | api, indexer | `redis`, `6379` | The indexer needs them to expire the cache |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | indexer | from `docs/PIPELINE.md` | Counted in words |
| `TOP_K` | api | `5` | |
| `FETCH_K` | api | `20` | Candidates before re-ranking |
| `RELEVANCE_FLOOR` | api | from `docs/PIPELINE.md` | Below it the API abstains without calling the model |
| `CACHE_ENABLED` | api | `true` | Must be `true` in the cluster; `/readyz` then requires Redis |
| `CACHE_THRESHOLD` | api | from `docs/PIPELINE.md` | Cosine similarity for a cache hit |
| `CACHE_TTL_SECONDS`, `CACHE_MAX_ENTRIES` | api | `21600`, `200` | |
| `TEMPERATURE` | api | `0.2` | Facts and JSON belong at 0 to 0.3 |
| `LLM_PROVIDER`, `LLM_MODEL` | api | `ollama-host`, `llama3.2:3b` | |
| `LLM_NUM_CTX` | api | `8192` | Ollama truncates silently when the prompt overflows its window |
| `RETRIEVER` | api | `chroma` | `stub` only while the cluster runs without an index |
| `LLM_API_KEY` | api | (Secret) | Hosted mode only. Never in a ConfigMap |

Failure-injection switches, all default to the healthy value and exist only for
`docs/FAILURE-ANALYSIS.md`: `SKIP_OCR` (indexer), `CHUNK_MODE=fixed` (indexer),
`INCLUDE_SUPERSEDED` (api), `PROMPT_GROUNDING` (api).

## Entry points
| What | Command |
| --- | --- |
| Indexer Job and CronJob | `python -m pipeline.run` (same image, same args) |
| Indexer image needs | `tesseract-ocr`, `poppler-utils` (apt) and `requirements.txt` |
| Index inspection (no model, no Chroma) | `python -m pipeline.run --dry-run --dump chunks.jsonl` |
| API | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |

## HTTP
`POST /api/ask` `{question}` returns `AskResponse` (see `api/app/schemas.py`). Additions to the
starter's contract, all optional with defaults: `cached` (null, true or false), `citations_dropped`.
`GET /healthz` touches nothing. `GET /readyz` returns 200 or 503 with `checks` and `failed`.

## Resource facts for the platform side
The indexer's memory is dominated by PDF extraction and OCR (300 dpi page images), not by
embedding. Measure with `kubectl top pods` while the Job runs and set the limit from that.
The API is I/O-bound while the model generates.
