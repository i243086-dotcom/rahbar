"""Indexer configuration, from the same ConfigMap the API reads (section 4.1).

Every value is an environment variable, so the Job and the CronJob run the same image
with the same ConfigMap as the API. Unit: CHUNK_SIZE and CHUNK_OVERLAP are counted in
WORDS (whitespace-separated tokens), see docs/PIPELINE.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class IndexerSettings:
    embed_model: str        # EMBED_MODEL: must equal the API's value (section 4.4)
    chroma_host: str
    chroma_port: int
    collection: str
    corpus_dir: str         # where the documents and _index.json sit inside the Job's pod
    chunk_size: int         # words
    chunk_overlap: int      # words
    ollama_url: str
    # Cache invalidation (section 3.3): the indexer expires the API's semantic cache.
    redis_host: str = ""    # empty = no cache to invalidate (local runs, CI without Redis)
    redis_port: int = 6379
    # Failure-injection switches for docs/FAILURE-ANALYSIS.md. Defaults are the healthy values.
    skip_ocr: bool = False          # stage A: index scanned pages without OCR
    chunk_mode: str = "structure"   # stage B: "structure" (shipped) or "fixed"
    embed_batch: int = 16


def get_settings() -> IndexerSettings:
    return IndexerSettings(
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=int(os.environ.get("CHROMA_PORT", 8000)),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        corpus_dir=os.environ.get("CORPUS_DIR", "/corpus"),
        chunk_size=int(os.environ.get("CHUNK_SIZE", 400)),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", 50)),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        redis_host=os.environ.get("REDIS_HOST", ""),
        redis_port=int(os.environ.get("REDIS_PORT", 6379)),
        skip_ocr=_bool("SKIP_OCR"),
        chunk_mode=os.environ.get("CHUNK_MODE", "structure"),
        embed_batch=int(os.environ.get("EMBED_BATCH", 16)),
    )
