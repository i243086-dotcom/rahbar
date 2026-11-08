from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.providers.llm.base import InvalidModelOutput, ProviderError, parse_answer
from app.providers.llm.hosted import HostedProvider
from app.providers.llm.ollama import OllamaProvider
from app.retrieval.chroma import IndexInfo
from app.services.readiness import check_readiness, pin_mismatch

from .conftest import make_settings, passage

VALID = {"reasoning": "r", "answer": "80 percent", "answered_from_context": True,
         "confidence": "high", "citations": [{"source": "a.md", "section": "1", "page": 1}]}


# ------------------------------------------------------------------------------ the pin (4.4)
def test_pin_mismatch_names_exactly_what_conflicts() -> None:
    msg = pin_mismatch({"embed_model": "dummy-768", "dimension": 768},
                       make_settings(embed_model="nomic-embed-text"))
    assert msg and "dummy-768" in msg and "nomic-embed-text" in msg and "768" in msg
    assert "mismatch" in msg


def test_pin_matches_when_models_agree() -> None:
    assert pin_mismatch({"embed_model": "nomic-embed-text"},
                        make_settings(embed_model="nomic-embed-text")) is None


def test_an_index_with_no_recorded_model_is_not_trusted() -> None:
    assert pin_mismatch({}, make_settings()) is not None


class Retr:
    def __init__(self, info: IndexInfo | Exception) -> None:
        self._info = info

    def info(self) -> IndexInfo:
        if isinstance(self._info, Exception):
            raise self._info
        return self._info


def state(info: IndexInfo | Exception, **settings: Any) -> SimpleNamespace:
    s = make_settings(retriever="chroma", embed_model="nomic-embed-text", **settings)
    return SimpleNamespace(settings=s, retriever=Retr(info), cache=None)


def test_ready_when_everything_is_in_order() -> None:
    ready, checks = check_readiness(state(IndexInfo(5, {"embed_model": "nomic-embed-text"})))
    assert ready and checks["collection"].startswith("ok")


def test_not_ready_on_an_empty_collection() -> None:
    ready, checks = check_readiness(state(IndexInfo(0, {"embed_model": "nomic-embed-text"})))
    assert not ready and "empty" in checks["collection"]


def test_not_ready_on_a_model_mismatch() -> None:
    ready, checks = check_readiness(state(IndexInfo(5, {"embed_model": "dummy-768"})))
    assert not ready and "mismatch" in checks["embedding_pin"]


def test_not_ready_when_chroma_is_unreachable() -> None:
    ready, checks = check_readiness(state(ConnectionError("no route to chroma")))
    assert not ready and checks["chroma"].startswith("unreachable")


def test_not_ready_when_redis_is_unreachable() -> None:
    class DeadCache:
        def ping(self) -> None:
            raise ConnectionError("redis down")

    st = state(IndexInfo(5, {"embed_model": "nomic-embed-text"}), cache_enabled=True)
    st.cache = DeadCache()
    ready, checks = check_readiness(st)
    assert not ready and checks["redis"].startswith("unreachable")


def test_readyz_returns_503_and_names_the_failed_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVER", "stub")
    from app.main import app

    with TestClient(app) as client:
        app.state.settings = make_settings(retriever="chroma", embed_model="nomic-embed-text")
        app.state.retriever = Retr(IndexInfo(5, {"embed_model": "dummy-768"}))
        r = client.get("/readyz")
        assert r.status_code == 503 and r.json()["failed"] == "embedding_pin"
        assert client.get("/healthz").status_code == 200         # liveness is unaffected


# ------------------------------------------------------------------------------ providers
def test_parse_answer_accepts_fenced_json_and_rejects_prose() -> None:
    assert parse_answer("```json\n" + json.dumps(VALID) + "\n```").answer == "80 percent"
    with pytest.raises(InvalidModelOutput):
        parse_answer("Sure! The answer is 80 percent.")
    with pytest.raises(InvalidModelOutput):
        parse_answer(json.dumps({"answer": "missing keys"}))


def client_returning(payload: dict[str, Any], status: int = 200) -> tuple[httpx.Client, list[Any]]:
    seen: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_ollama_sends_the_schema_low_temperature_and_a_big_context() -> None:
    http, seen = client_returning({"message": {"content": json.dumps(VALID)},
                                   "prompt_eval_count": 900, "eval_count": 60})
    s = make_settings(temperature=0.2, llm_num_ctx=8192)
    answer = OllamaProvider(s, http).generate("q?", [passage(1)])
    body = json.loads(seen[0].content)
    assert answer.answered_from_context and body["stream"] is False
    assert body["format"]["properties"].keys() >= {"answer", "citations", "answered_from_context"}
    assert body["options"] == {"temperature": 0.2, "num_ctx": 8192}


def test_ollama_prose_reply_raises_invalid_model_output() -> None:
    http, _ = client_returning({"message": {"content": "I think it is 80 percent."}})
    with pytest.raises(InvalidModelOutput):
        OllamaProvider(make_settings(), http).generate("q?", [passage(1)])


def test_ollama_http_error_is_a_provider_error() -> None:
    http, _ = client_returning({"error": "model not found"}, status=404)
    with pytest.raises(ProviderError):
        OllamaProvider(make_settings(), http).generate("q?", [passage(1)])


def test_hosted_provider_needs_a_key_and_never_leaks_it() -> None:
    with pytest.raises(ProviderError):
        HostedProvider(make_settings(hosted_base_url="https://x/v1", llm_api_key="")).generate(
            "q?", [passage(1)])
    http, seen = client_returning({"error": "bad key"}, status=401)
    s = make_settings(hosted_base_url="https://api.example/v1", llm_api_key="SECRET-KEY-123")
    with pytest.raises(ProviderError) as exc:
        HostedProvider(s, http).generate("q?", [passage(1)])
    assert "SECRET-KEY-123" not in str(exc.value) and "401" in str(exc.value)
    assert seen[0].headers["authorization"] == "Bearer SECRET-KEY-123"


def test_hosted_provider_parses_an_openai_style_reply() -> None:
    http, _ = client_returning({"choices": [{"message": {"content": json.dumps(VALID)}}],
                                "usage": {"prompt_tokens": 800, "completion_tokens": 50}})
    s = make_settings(hosted_base_url="https://api.example/v1", llm_api_key="k")
    assert HostedProvider(s, http).generate("q?", [passage(1)]).confidence == "high"


def test_query_embedder_uses_the_pinned_model_and_query_prefix() -> None:
    from app.retrieval.embedder import EmbeddingError, OllamaEmbedder

    http, seen = client_returning({"embeddings": [[0.1, 0.2]]})
    emb = OllamaEmbedder(make_settings(embed_model="nomic-embed-text"), http)
    assert emb.embed_query("hello") == [0.1, 0.2]
    body = json.loads(seen[0].content)
    assert body["model"] == "nomic-embed-text" and body["input"] == ["search_query: hello"]
    bad, _ = client_returning({"error": "x"}, status=500)
    with pytest.raises(EmbeddingError):
        OllamaEmbedder(make_settings(), bad).embed_query("hello")
