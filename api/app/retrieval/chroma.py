"""The real retriever (sections 3.2 and 4.4). It only ever READS the index.

Pipeline: embed the question, query the top FETCH_K by cosine similarity with a metadata
filter that excludes superseded documents, add exact-term matches (hybrid), re-rank, return
the top k. Chroma returns cosine *distance*; Passage.score is similarity = 1 - distance.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..schemas import Passage
from .embedder import OllamaEmbedder
from .exact import contains_term, exact_terms
from .versions import wants_older

log = logging.getLogger("rahbar.retrieval")

COLLECTION_TTL = 15.0     # seconds: how long a collection handle is reused before re-resolving


@dataclass
class IndexInfo:
    count: int
    metadata: dict[str, Any]


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings, embedder: Any | None = None,
                 client: Any | None = None) -> None:
        self.settings = settings
        if client is None:
            import chromadb  # the thin client, from chromadb-client in requirements.txt
            from chromadb.config import Settings as ChromaSettings

            client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                                         settings=ChromaSettings(anonymized_telemetry=False))
        self.client = client
        self.embedder = embedder or OllamaEmbedder(settings)
        self._lock = threading.Lock()
        self._collection: Any = None
        self._resolved_at = 0.0

    # ------------------------------------------------------------------ collection handle
    def _get_collection(self, fresh: bool = False) -> Any:
        """The live collection. The indexer replaces it by name on every re-index, so the
        handle is re-resolved every COLLECTION_TTL seconds and on any error."""
        with self._lock:
            if fresh or self._collection is None or time.monotonic() - self._resolved_at > COLLECTION_TTL:
                self._collection = self.client.get_collection(self.settings.collection)
                self._resolved_at = time.monotonic()
            return self._collection

    def info(self) -> IndexInfo:
        """Live facts about the index, for /readyz. Always asks Chroma; never cached."""
        collection = self._get_collection(fresh=True)
        return IndexInfo(count=int(collection.count()), metadata=dict(collection.metadata or {}))

    def index_id(self) -> str:
        try:
            return str(self._get_collection().metadata.get("index_id", "unknown"))
        except Exception:     # noqa: BLE001 - a cache key must never break a request
            return "unknown"

    def _superseded_versions(self) -> list[str]:
        try:
            raw = str(self._get_collection().metadata.get("superseded_versions", ""))
        except Exception:     # noqa: BLE001
            return []
        return [v for v in raw.split(",") if v]

    # ------------------------------------------------------------------ the retriever contract
    def embed_query(self, question: str) -> list[float]:
        return self.embedder.embed_query(question)       # type: ignore[no-any-return]

    def scope(self, question: str) -> str:
        if self.settings.include_superseded:
            return "all"
        return "all" if wants_older(question, self._superseded_versions()) else "current"

    def retrieve(
        self, question: str, k: int, query_vector: list[float] | None = None
    ) -> list[Passage]:
        vector = query_vector if query_vector is not None else self.embed_query(question)
        where = None if self.scope(question) == "all" else {"superseded": False}
        pool = max(self.settings.fetch_k, k)

        candidates: dict[str, Passage] = {}
        for p in self._query(vector, pool, where, None):
            candidates[p.chunk_id] = p
        terms = exact_terms(question)
        for term in terms:                                  # the hybrid half
            for p in self._query(vector, k, where, {"$contains": term}):
                candidates.setdefault(p.chunk_id, p)
        for p in candidates.values():
            p.exact_match = bool(terms) and contains_term(p.text, terms)

        return self._rank(list(candidates.values()), k)

    def _rank(self, candidates: list[Passage], k: int) -> list[Passage]:
        """Top k by similarity plus a small boost for exact-term chunks, with slots reserved
        for them. A boost alone cannot rescue a chunk whose vector is far from the question
        (that is exactly the case embeddings get wrong), so up to k // 2 slots (at least one)
        go to the best chunks that literally contain the term."""
        boost = self.settings.exact_boost

        def key(p: Passage) -> float:
            return p.score + (boost if p.exact_match else 0.0)

        ranked = sorted(candidates, key=key, reverse=True)
        reserved = [p for p in ranked if p.exact_match][:max(1, k // 2)]
        taken = {p.chunk_id for p in reserved}
        rest = [p for p in ranked if p.chunk_id not in taken][:k - len(reserved)]
        return sorted(reserved + rest, key=key, reverse=True)

    def _query(self, vector: list[float], n: int, where: dict[str, Any] | None,
               where_document: dict[str, Any] | None) -> list[Passage]:
        kwargs: dict[str, Any] = {
            "query_embeddings": [vector], "n_results": n,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        if where_document:
            kwargs["where_document"] = where_document
        try:
            res = self._get_collection().query(**kwargs)
        except Exception:     # noqa: BLE001 - the collection may have been swapped by a re-index
            res = self._get_collection(fresh=True).query(**kwargs)
        passages = []
        for chunk_id, text, meta, distance in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0],
            strict=True,
        ):
            passages.append(Passage(
                chunk_id=chunk_id, text=text, source=str(meta.get("source", "")),
                section=str(meta.get("section", "")), page=meta.get("page"),
                score=round(1.0 - float(distance), 4),
                doc_version=str(meta.get("doc_version", "")) or None,
                superseded=bool(meta.get("superseded", False)),
            ))
        return passages
