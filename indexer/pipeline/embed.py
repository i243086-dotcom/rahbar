"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .config import IndexerSettings

# nomic-embed-text was trained with task prefixes. Documents and queries get different ones,
# and the API (api/app/retrieval/embedder.py) must use the matching query prefix.
DOCUMENT_PREFIX = "search_document: "


def prefix_for(model: str) -> str:
    return DOCUMENT_PREFIX if model.startswith("nomic-embed-text") else ""


def embed(texts: list[str], settings: IndexerSettings,
          client: httpx.Client | None = None) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    POST {ollama_url}/api/embed with {"model": ..., "input": [texts]} returns
    {"embeddings": [[...], ...]}. Calls are batched; one request per chunk is slow.
    Raises RuntimeError if the server returns the wrong number of vectors or vectors of
    different lengths, because a silent gap would shift every later chunk's vector.
    """
    if not texts:
        return []
    prefix = prefix_for(settings.embed_model)
    own = client is None
    http = client or httpx.Client(timeout=300.0)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), settings.embed_batch):
            batch = [prefix + t for t in texts[start:start + settings.embed_batch]]
            vectors.extend(_embed_batch(http, settings, batch))
    finally:
        if own:
            http.close()
    dims = {len(v) for v in vectors}
    if len(vectors) != len(texts) or len(dims) != 1:
        raise RuntimeError(f"embedding returned {len(vectors)} vectors of sizes {sorted(dims)} "
                           f"for {len(texts)} texts")
    return vectors


def _embed_batch(http: httpx.Client, settings: IndexerSettings,
                 batch: list[str]) -> list[list[float]]:
    last: Exception | None = None
    for attempt in range(4):
        try:
            r = http.post(f"{settings.ollama_url.rstrip('/')}/api/embed",
                          json={"model": settings.embed_model, "input": batch})
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            embeddings = data["embeddings"]
            if len(embeddings) != len(batch):
                raise RuntimeError(f"asked for {len(batch)} embeddings, got {len(embeddings)}")
            return [list(map(float, e)) for e in embeddings]
        except (httpx.HTTPError, KeyError, RuntimeError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"embedding failed after retries: {last!r}")
