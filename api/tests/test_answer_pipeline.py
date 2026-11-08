from __future__ import annotations

import fakeredis
import pytest

from app.providers.llm.base import InvalidModelOutput, ProviderError
from app.schemas import Answer, Citation
from app.services.answer import ABSTAIN_TEXT, FALLBACK_TEXT, answer_question
from app.services.cache import SemanticCache

from .conftest import FakeRetriever, ScriptedProvider, good_answer, make_settings, passage


def cache_for(settings, vector_store=None) -> SemanticCache:  # noqa: ANN001
    return SemanticCache(settings, client=vector_store or fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture()
def settings():  # noqa: ANN201
    return make_settings(top_k=3, relevance_floor=0.45, cache_enabled=True, cache_threshold=0.92)


def test_grounded_answer_cites_a_retrieved_chunk(settings) -> None:  # noqa: ANN001
    r = answer_question("What is the attendance rule?", FakeRetriever([passage(1)]),
                        ScriptedProvider(good_answer()), settings)
    assert r.answered_from_context and r.citations[0].section == "1. Attendance"
    assert r.citations_dropped == 0 and [x.chunk_id for x in r.retrieved] == ["c1"]


def test_abstains_below_the_relevance_floor_without_calling_the_model(settings) -> None:  # noqa: ANN001
    provider = ScriptedProvider(good_answer())
    r = answer_question("How do I get a hostel room?", FakeRetriever([passage(1, score=0.30)]),
                        provider, settings)
    assert r.answered_from_context is False and r.answer == ABSTAIN_TEXT
    assert r.citations == [] and provider.calls == 0


def test_an_exact_match_passes_the_floor_even_with_a_low_score(settings) -> None:  # noqa: ANN001
    p = passage(1, score=0.20, exact_match=True)
    r = answer_question("What is clause 1.21?", FakeRetriever([p]), ScriptedProvider(good_answer()),
                        settings)
    assert r.answered_from_context is True


def test_the_model_can_abstain_itself(settings) -> None:  # noqa: ANN001
    declined = Answer(reasoning="r", answer="The documents do not cover this.", citations=[],
                      answered_from_context=False, confidence="low")
    r = answer_question("Q about hostels?", FakeRetriever([passage(1, score=0.6)]),
                        ScriptedProvider(declined), settings)
    assert r.answered_from_context is False and r.citations == []


def test_invalid_output_is_retried_once_in_strict_mode_then_succeeds(settings) -> None:  # noqa: ANN001
    provider = ScriptedProvider(InvalidModelOutput("prose, not JSON"), good_answer())
    r = answer_question("What is the attendance rule?", FakeRetriever([passage(1)]), provider,
                        settings)
    assert r.answered_from_context and provider.calls == 2
    assert provider.strict_flags == [False, True]


def test_two_failures_return_the_canned_fallback_never_an_exception(settings) -> None:  # noqa: ANN001
    provider = ScriptedProvider(InvalidModelOutput("prose"), ProviderError("boom"))
    r = answer_question("What is the attendance rule?", FakeRetriever([passage(1)]), provider,
                        settings)
    assert r.answer == FALLBACK_TEXT and r.answered_from_context is False
    assert provider.calls == 2


def test_fabricated_citations_are_never_returned(settings) -> None:  # noqa: ANN001
    mixed = Answer(reasoning="r", answer="80 percent.", answered_from_context=True,
                   confidence="high",
                   citations=[Citation(source="rules-2026.md", section="1. Attendance", page=1),
                              Citation(source="ghost.pdf", section="7.7", page=9)])
    r = answer_question("What is the attendance rule?", FakeRetriever([passage(1)]),
                        ScriptedProvider(mixed), settings)
    assert [c.source for c in r.citations] == ["rules-2026.md"] and r.citations_dropped == 1


def test_a_retrieval_or_embedding_outage_is_a_fallback_not_a_500(settings) -> None:  # noqa: ANN001
    class Broken(FakeRetriever):
        def embed_query(self, question: str):  # noqa: ANN201
            raise RuntimeError("ollama is down")

    r = answer_question("What is the attendance rule?", Broken([passage(1)]),
                        ScriptedProvider(good_answer()), settings)
    assert r.answer == FALLBACK_TEXT


# ------------------------------------------------------------------------------------- cache
def test_second_similar_question_is_served_from_cache(settings) -> None:  # noqa: ANN001
    retriever, provider = FakeRetriever([passage(1)]), ScriptedProvider(good_answer())
    cache = cache_for(settings)
    first = answer_question("What is the attendance rule?", retriever, provider, settings, cache)
    second = answer_question("What is the rule on attendance?", retriever, provider, settings, cache)
    assert first.cached is False and second.cached is True
    assert second.answer == first.answer and provider.calls == 1 and retriever.retrieve_calls == 1


def test_abstentions_followups_and_failures_are_never_cached(settings) -> None:  # noqa: ANN001
    cache = cache_for(settings)
    # abstention
    answer_question("Q about hostels?", FakeRetriever([passage(1, score=0.1)]),
                    ScriptedProvider(good_answer()), settings, cache)
    # follow-up
    answer_question("and what about that one?", FakeRetriever([passage(1)]),
                    ScriptedProvider(good_answer()), settings, cache)
    # failed validation
    answer_question("What is the attendance rule?", FakeRetriever([passage(1)]),
                    ScriptedProvider(ProviderError("x")), settings, cache)
    assert cache.redis.hlen("rahbar:cache:vecs") == 0


def test_cache_never_crosses_scope_or_index_build(settings) -> None:  # noqa: ANN001
    cache = cache_for(settings)
    provider = ScriptedProvider(good_answer())
    answer_question("What is the attendance rule?", FakeRetriever([passage(1)], scope="current"),
                    provider, settings, cache)
    older = answer_question("What is the attendance rule?",
                            FakeRetriever([passage(1)], scope="all"), provider, settings, cache)
    assert older.cached is False                      # a "current" answer is not served for "older"

    class NewIndex(FakeRetriever):
        def index_id(self) -> str:
            return "idx2"

    after = answer_question("What is the attendance rule?", NewIndex([passage(1)]), provider,
                            settings, cache)
    assert after.cached is False                      # re-indexed: old entries are ignored


def test_invalidate_expires_everything(settings) -> None:  # noqa: ANN001
    cache = cache_for(settings)
    answer_question("What is the attendance rule?", FakeRetriever([passage(1)]),
                    ScriptedProvider(good_answer()), settings, cache)
    assert cache.invalidate() >= 2
    assert cache.redis.hlen("rahbar:cache:vecs") == 0


def test_a_dead_redis_degrades_to_a_miss(settings) -> None:  # noqa: ANN001
    class Dead:
        def __getattr__(self, name: str):  # noqa: ANN204
            raise ConnectionError("redis is down")

    r = answer_question("What is the attendance rule?", FakeRetriever([passage(1)]),
                        ScriptedProvider(good_answer()), settings, cache_for(settings, Dead()))
    assert r.answered_from_context is True


def test_cache_evicts_the_oldest_beyond_the_cap() -> None:
    s = make_settings(cache_enabled=True, cache_max_entries=2, cache_threshold=0.99)
    cache = cache_for(s)
    for i in range(4):
        cache.store(f"q{i}", [float(i + 1), 1.0], {"answer": str(i)}, "current", "idx")
    assert cache.redis.zcard("rahbar:cache:idx") == 2
    assert cache.redis.hlen("rahbar:cache:vecs") == 2
