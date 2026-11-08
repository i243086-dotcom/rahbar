"""Prometheus metrics at /metrics (section 4.8).

Request count and latency are wired up already. Add your own the same way:
retrieval latency, generation latency, cache hits, abstentions, fallbacks, tokens.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

router = APIRouter()

# Query-pipeline metrics (section 4.8)
RETRIEVAL_LATENCY = Histogram("rahbar_retrieval_seconds", "Embed + vector search latency",
                              buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5))
GENERATION_LATENCY = Histogram("rahbar_generation_seconds", "LLM generation latency",
                               buckets=(0.5, 1, 2, 5, 10, 20, 40, 80, 160))
CACHE_LOOKUPS = Counter("rahbar_cache_lookups_total", "Semantic cache lookups", ["result"])
CACHE_HIT_RATIO = Gauge("rahbar_cache_hit_ratio", "Cache hits / lookups since this pod started")
ABSTENTIONS = Counter("rahbar_abstentions_total", "Answers declined as not covered", ["reason"])
FALLBACKS = Counter("rahbar_fallbacks_total", "Canned fallback responses served", ["reason"])
TOKENS_IN = Histogram("rahbar_llm_tokens_in", "Prompt tokens per generation",
                      buckets=(250, 500, 1000, 2000, 3000, 4000, 6000, 8000))
TOKENS_OUT = Histogram("rahbar_llm_tokens_out", "Completion tokens per generation",
                       buckets=(25, 50, 100, 200, 400, 800))
CITATIONS_DROPPED = Counter("rahbar_citations_dropped_total",
                            "Model citations that matched no retrieved chunk (fabricated)")
INJECTION_REMOVED = Counter("rahbar_injection_sentences_removed_total",
                            "Instruction-like sentences removed from retrieved text")

_lookups = {"hit": 0, "total": 0}


def record_cache_lookup(hit: bool) -> None:
    _lookups["total"] += 1
    _lookups["hit"] += int(hit)
    CACHE_LOOKUPS.labels(result="hit" if hit else "miss").inc()
    CACHE_HIT_RATIO.set(_lookups["hit"] / _lookups["total"])

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
