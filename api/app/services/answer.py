"""Turns a question into an AskResponse: the query pipeline of section 3.2.

    1. receive + validate (FastAPI/Pydantic, 3 to 500 characters)
    2. cache check                      services/cache.py, never for follow-ups
    3. embed the question               retrieval/embedder.py (the pinned model)
    4. retrieve top-k                   retrieval/chroma.py (superseded filter, exact terms)
    5. augment                          services/prompt.py (evidence is data)
    6. generate                         providers/llm/* (schema-constrained, low temperature)
    7. validate: parse, check citations, retry once, then fall back
    8. store the cache entry when it is safe (services/policy.py)

Every step that can fail ends in a well-formed AskResponse, never a 500.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import InvalidModelOutput, LLMProvider, ProviderError, usage_var
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import Answer, AskResponse, Citation, Passage, RetrievedRef
from .cache import SemanticCache
from .citations import reconcile
from .guard import looks_like_injection
from .policy import is_followup, should_cache

log = logging.getLogger("rahbar.answer")

ABSTAIN_TEXT = ("I could not find this in the documents I have been given, so I will not guess. "
                "Please check with the university office or the official website.")
FALLBACK_TEXT = ("I could not produce a reliable answer right now. Please try again in a moment, "
                 "or check with the university office.")


def passes_floor(p: Passage, floor: float) -> bool:
    """Relevant enough to answer from: similar enough, or it literally contains the exact term
    (clause number, course code, amount) the student asked about."""
    return p.score >= floor or p.exact_match


def _refs(passages: list[Passage]) -> list[RetrievedRef]:
    return [RetrievedRef(chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page,
                         score=p.score) for p in passages]


def _generate_validated(
    question: str, passages: list[Passage], provider: LLMProvider
) -> tuple[Answer | None, list[Citation], int, str]:
    """Generate, validate, retry once. Returns (answer, valid citations, dropped, failure)."""
    failure = ""
    dropped_total = 0
    for attempt in range(2):
        try:
            retry = attempt == 1            # the one retry adds a stricter reminder to the prompt
            answer = provider.generate(question, passages, strict=retry)
            citations, dropped = reconcile(answer.citations, passages)
            dropped_total += dropped
            if dropped:
                metrics.CITATIONS_DROPPED.inc(dropped)
                log.warning("fabricated citations dropped",
                            extra={"dropped": dropped, "attempt": attempt + 1})
            if answer.answered_from_context and not citations:
                raise InvalidModelOutput("the answer claims to be grounded but cites nothing retrieved")
            return answer, citations, dropped_total, ""
        except ProviderError as exc:
            failure = f"{type(exc).__name__}: {exc}"
            log.warning("generation attempt failed", extra={"attempt": attempt + 1, "error": failure})
    return None, [], dropped_total, failure


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings,
    cache: SemanticCache | None = None,
) -> AskResponse:
    rid = request_id_var.get()
    followup = is_followup(question)
    flagged = looks_like_injection(question)

    def respond(answer: str, citations: list[Citation], grounded: bool, confidence: Any,
                passages: list[Passage], *, cached: bool | None, dropped: int = 0) -> AskResponse:
        return AskResponse(
            request_id=rid, answer=answer, citations=citations, answered_from_context=grounded,
            confidence=confidence, retrieved=_refs(passages), provider=provider.name,
            cached=cached, citations_dropped=dropped)

    cached_flag: bool | None = False if cache is not None else None
    started = time.perf_counter()
    try:
        vector = retriever.embed_query(question)
        scope = retriever.scope(question)
        index_id = retriever.index_id()
    except Exception as exc:     # noqa: BLE001 - embedding service down, collection missing, ...
        metrics.FALLBACKS.labels(reason="embedding_error").inc()
        log.error("embedding failed", extra={"error": repr(exc)}, exc_info=True)
        return respond(FALLBACK_TEXT, [], False, "low", [], cached=cached_flag)

    cacheable = cache is not None and vector is not None and not followup
    if cacheable:
        assert cache is not None and vector is not None
        hit = cache.lookup(vector, scope, index_id)
        metrics.record_cache_lookup(hit is not None)
        if hit is not None:
            hit = {**hit, "request_id": rid, "cached": True}
            log.info("answered", extra={"cache": "hit", "scope": scope, "follow_up": followup})
            return AskResponse(**hit)

    try:
        passages = retriever.retrieve(question, k=settings.top_k, query_vector=vector)
    except Exception as exc:     # noqa: BLE001
        metrics.FALLBACKS.labels(reason="retrieval_error").inc()
        log.error("retrieval failed", extra={"error": repr(exc)}, exc_info=True)
        return respond(FALLBACK_TEXT, [], False, "low", [], cached=cached_flag)
    metrics.RETRIEVAL_LATENCY.observe(time.perf_counter() - started)

    extra: dict[str, Any] = {
        "retriever": retriever.name, "provider": provider.name, "top_k": settings.top_k,
        "chunk_ids": [p.chunk_id for p in passages],
        "scores": [round(p.score, 4) for p in passages], "scope": scope,
        "follow_up": followup, "cache": "miss" if cacheable else "skipped",
        "question_flagged_as_injection": flagged,
    }

    # Honest abstention: nothing retrieved clears the relevance floor, so do not even ask the model.
    if not any(passes_floor(p, settings.relevance_floor) for p in passages):
        metrics.ABSTENTIONS.labels(reason="floor").inc()
        log.info("answered", extra={**extra, "answered_from_context": False,
                                    "abstention": "relevance_floor",
                                    "floor": settings.relevance_floor})
        return respond(ABSTAIN_TEXT, [], False, "low", passages, cached=cached_flag)

    t0 = time.perf_counter()
    usage_var.set({})
    answer, citations, dropped, failure = _generate_validated(question, passages, provider)
    metrics.GENERATION_LATENCY.observe(time.perf_counter() - t0)
    usage = usage_var.get()
    if usage:
        metrics.TOKENS_IN.observe(usage.get("tokens_in", 0))
        metrics.TOKENS_OUT.observe(usage.get("tokens_out", 0))
        if usage.get("injection_removed"):
            metrics.INJECTION_REMOVED.inc(usage["injection_removed"])
        extra.update(tokens_in=usage.get("tokens_in"), tokens_out=usage.get("tokens_out"),
                     injection_removed=usage.get("injection_removed", 0))

    if answer is None:                                    # validation failed twice: safe fallback
        metrics.FALLBACKS.labels(reason="generation_failed").inc()
        log.error("answered", extra={**extra, "answered_from_context": False,
                                    "fallback": True, "error": failure})
        return respond(FALLBACK_TEXT, [], False, "low", passages, cached=cached_flag,
                       dropped=dropped)

    if not answer.answered_from_context:                  # the model itself declined
        metrics.ABSTENTIONS.labels(reason="model").inc()
        log.info("answered", extra={**extra, "answered_from_context": False,
                                    "abstention": "model"})
        return respond(answer.answer or ABSTAIN_TEXT, [], False, "low", passages,
                       cached=cached_flag, dropped=dropped)

    response = respond(answer.answer, citations, True, answer.confidence, passages,
                       cached=cached_flag, dropped=dropped)
    log.info("answered", extra={**extra, "answered_from_context": True,
                                "citations": len(citations), "citations_dropped": dropped})
    if cacheable and should_cache(followup=followup, answered_from_context=True,
                                  citations=len(citations), citations_dropped=dropped,
                                  fallback=False):
        assert cache is not None and vector is not None
        cache.store(question, vector, response.model_dump(exclude={"request_id", "cached"}),
                    scope, index_id)
    return response
