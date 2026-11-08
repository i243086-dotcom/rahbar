"""Stage 5: Store. The only code in the whole system that writes to Chroma.

Re-index strategy (recorded in docs/adr/0001-indexer-as-job.md):
  1. Build the new index in a temporary collection "<name>__build". The API keeps serving
     from the live collection the whole time.
  2. Only when every chunk is written, delete the live collection and rename the build
     collection to the live name. A failed or killed Job therefore never leaves the API
     with a half-built or empty index: the old one is still there.
  3. The API re-resolves the collection by name, so it picks up the new one on its next
     query (it retries once if the swap lands between two calls).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from .config import IndexerSettings
from .models import Chunk

BATCH = 100


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def collection_metadata(settings: IndexerSettings, chunks: list[Chunk], dim: int,
                        index_id: str) -> dict[str, str | int | float | bool]:
    """What the API's pin check and cache read back (docs/CONTRACT.md)."""
    return {
        "hnsw:space": "cosine",
        "embed_model": settings.embed_model,     # the pin (section 4.4)
        "dimension": dim,                        # the pin, second half
        "index_id": index_id,                    # changes on every build; tags cache entries
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "chunk_count": len(chunks),
        "superseded_versions": ",".join(sorted({c.doc_version for c in chunks if c.superseded})),
    }


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings,
          client: Any | None = None) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count."""
    if not chunks:
        raise ValueError("refusing to replace the index with zero chunks")
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
    ids = [c.id for c in chunks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chunk ids: ids must be unique per document position")
    client = client or get_client(settings)
    dim = len(vectors[0])
    build_name = f"{settings.collection}__build"

    try:                                       # leftovers from a Job that was killed midway
        client.delete_collection(build_name)
    except Exception:
        pass
    index_id = uuid.uuid4().hex[:12]
    build = client.create_collection(
        name=build_name, metadata=collection_metadata(settings, chunks, dim, index_id))
    for start in range(0, len(chunks), BATCH):
        part = slice(start, start + BATCH)
        build.add(ids=ids[part], documents=[c.text for c in chunks[part]],
                  embeddings=vectors[part], metadatas=[c.metadata() for c in chunks[part]])
    if int(build.count()) != len(chunks):
        raise RuntimeError(f"wrote {build.count()} of {len(chunks)} chunks; keeping the old index")

    try:
        client.delete_collection(settings.collection)
    except Exception:                          # first ever run: nothing to replace
        pass
    build.modify(name=settings.collection)
    return len(chunks)
