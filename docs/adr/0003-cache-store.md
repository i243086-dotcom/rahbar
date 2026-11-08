# ADR 0003: Redis for the semantic cache, not a second Chroma collection

## Status
Accepted · 2026-11-07

## Context
The same question, reworded, should not pay for retrieval and generation twice. A cache hit is
a question whose embedding is close to a cached one. The case study allows Redis or a second
Chroma collection. The architecture also says the indexer is the only writer to Chroma.

## Decision
Redis, with entries under the prefix `rahbar:cache:`: a hash of float32 vectors, a sorted set for
eviction order, and one JSON string per entry with a TTL. Lookup reads the vectors and scores them
in the API process. A hit needs cosine similarity at or above `CACHE_THRESHOLD`, the same scope
(current vs older versions) and the same `index_id`. The indexer deletes the whole prefix after a
re-index; the `index_id` check makes a stale entry harmless even if that delete fails or races an
in-flight request.

## Options considered
- **Second Chroma collection.** Native nearest-neighbour search, but the API would have to write
  to Chroma, breaking "one writer, one reader" and widening the NetworkPolicy. Entries would also
  need their own expiry code.
- **Redis Stack (RediSearch vector index).** The proper tool at scale, but a heavier image and
  more moving parts than a course project needs.
- **Exact-match cache on the normalised question.** Safe, but it misses every rewording, which
  is the whole point.

## Consequences
Redis gives TTL, eviction and cheap invalidation for free and keeps Chroma read-only for the API.
The cost is that lookup is linear in the number of entries, so `CACHE_MAX_ENTRIES` is capped (200);
beyond a few thousand entries the upgrade is a vector index. A dead Redis degrades to a cache miss
on the request path, but `/readyz` still fails so the pod is withheld from the Service.
What is never cached: follow-ups, abstentions, fallbacks, and any answer with a dropped citation.
The threshold is chosen with `eval/cache_threshold.py`: the lowest value with zero false hits
(`docs/PIPELINE.md`).
