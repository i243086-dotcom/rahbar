"""Semantic cache on Redis (section 3.3, docs/adr/0003-cache-store.md).

A hit is a question whose embedding has cosine similarity >= CACHE_THRESHOLD with a cached
one, for the same scope (current vs older versions) and the same index build.

Layout, all under the prefix the indexer expires after a re-index (pipeline/cache.py):
    rahbar:cache:idx     ZSET   entry id -> created time        (eviction order)
    rahbar:cache:vecs    HASH   "<id>|<scope>|<index_id>" -> float32 vector, base64
    rahbar:cache:e:<id>  STRING JSON {question, response}, with a TTL

Lookup reads the vector hash and scores in process. That is fine for a few hundred entries
(CACHE_MAX_ENTRIES) and is the stated trade-off in the ADR; Redis Stack or a vector index is
the upgrade path.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import time
import uuid
from array import array
from typing import Any

from ..config import Settings

log = logging.getLogger("rahbar.cache")

PREFIX = "rahbar:cache:"
IDX, VECS, ENTRY = f"{PREFIX}idx", f"{PREFIX}vecs", f"{PREFIX}e:"


def encode(vector: list[float]) -> str:
    return base64.b64encode(array("f", vector).tobytes()).decode("ascii")


def decode(blob: str) -> list[float]:
    a = array("f")
    a.frombytes(base64.b64decode(blob))
    return list(a)


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class SemanticCache:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.threshold = settings.cache_threshold
        self.ttl = settings.cache_ttl_seconds
        self.max_entries = settings.cache_max_entries
        if client is None:
            import redis

            client = redis.Redis(host=settings.redis_host, port=settings.redis_port,
                                 socket_timeout=2, socket_connect_timeout=2,
                                 decode_responses=True)
        self.redis: Any = client

    def ping(self) -> None:
        """Raises when Redis is unreachable; /readyz turns that into a 503."""
        self.redis.ping()

    def lookup(self, vector: list[float], scope: str, index_id: str) -> dict[str, Any] | None:
        """The cached response for a similar-enough question, or None. Never raises: a broken
        cache must degrade to a miss, not to an error."""
        try:
            suffix = f"|{scope}|{index_id}"
            best_id, best_sim = None, -1.0
            for field, blob in self.redis.hgetall(VECS).items():
                if not field.endswith(suffix):
                    continue                      # other scope, or an entry from an older index
                sim = cosine(vector, decode(blob))
                if sim > best_sim:
                    best_id, best_sim = field.split("|", 1)[0], sim
            if best_id is None or best_sim < self.threshold:
                return None
            raw = self.redis.get(f"{ENTRY}{best_id}")
            if raw is None:                       # the entry expired; tidy its vector
                self._forget(best_id)
                return None
            entry = json.loads(raw)
            response: dict[str, Any] = entry["response"]
            log.info("cache hit", extra={"similarity": round(best_sim, 4),
                                         "cached_question": entry.get("question", "")[:80]})
            return response
        except Exception as exc:     # noqa: BLE001
            log.warning("cache lookup failed", extra={"error": repr(exc)})
            return None

    def store(self, question: str, vector: list[float], response: dict[str, Any], scope: str,
              index_id: str) -> None:
        try:
            entry_id = uuid.uuid4().hex
            self.redis.set(f"{ENTRY}{entry_id}",
                           json.dumps({"question": question, "response": response}),
                           ex=self.ttl)
            self.redis.hset(VECS, f"{entry_id}|{scope}|{index_id}", encode(vector))
            self.redis.zadd(IDX, {entry_id: time.time()})
            excess = int(self.redis.zcard(IDX)) - self.max_entries
            if excess > 0:                        # evict the oldest entries
                for old_id, _ in self.redis.zpopmin(IDX, excess):
                    self._forget(old_id, from_index=False)
        except Exception as exc:     # noqa: BLE001
            log.warning("cache store failed", extra={"error": repr(exc)})

    def _forget(self, entry_id: str, from_index: bool = True) -> None:
        for field in [f for f in self.redis.hkeys(VECS) if f.startswith(f"{entry_id}|")]:
            self.redis.hdel(VECS, field)
        self.redis.delete(f"{ENTRY}{entry_id}")
        if from_index:
            self.redis.zrem(IDX, entry_id)

    def invalidate(self) -> int:
        """Delete every entry. The indexer does the same after a re-index; this is for tests
        and for an operator who wants a clean cache without re-indexing."""
        keys = list(self.redis.scan_iter(match=f"{PREFIX}*", count=500))
        if keys:
            self.redis.delete(*keys)
        return len(keys)
