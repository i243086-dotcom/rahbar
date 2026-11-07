"""Fakes shared by the API tests: no Chroma, no Redis server, no model, no network."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.schemas import Answer, Citation, Passage


def passage(i: int = 1, section: str = "1. Attendance", score: float = 0.8, **kw: Any) -> Passage:
    base: dict[str, Any] = {
        "chunk_id": f"c{i}", "text": f"Text of chunk {i}.", "source": "rules-2026.md",
        "section": section, "page": 1, "score": score, "doc_version": "2026", "superseded": False}
    return Passage(**{**base, **kw})


def make_settings(**kw: Any) -> Settings:
    return Settings(**{"retriever": "stub", "llm_provider": "stub", **kw})


class FakeRetriever:
    name = "fake"

    def __init__(self, passages: list[Passage], vector: list[float] | None = None,
                 scope: str = "current") -> None:
        self.passages, self.vector, self._scope = passages, vector or [1.0, 0.0], scope
        self.retrieve_calls = 0

    def embed_query(self, question: str) -> list[float] | None:
        return self.vector

    def scope(self, question: str) -> str:
        return self._scope

    def index_id(self) -> str:
        return "idx1"

    def retrieve(self, question: str, k: int, query_vector: list[float] | None = None) -> list[Passage]:
        self.retrieve_calls += 1
        return [p.model_copy() for p in self.passages[:k]]


class ScriptedProvider:
    """Returns (or raises) what it is told, one item per call."""

    name = "scripted"

    def __init__(self, *script: Any) -> None:
        self.script, self.calls, self.strict_flags = list(script), 0, []

    def generate(self, question: str, passages: list[Passage], *, strict: bool = False) -> Answer:
        self.calls += 1
        self.strict_flags.append(strict)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[no-any-return]


def good_answer(section: str = "1. Attendance", source: str = "rules-2026.md") -> Answer:
    return Answer(reasoning="r", answer="You need 80 percent attendance.",
                  citations=[Citation(source=source, section=section, page=1)],
                  answered_from_context=True, confidence="high")


@pytest.fixture()
def settings() -> Settings:
    return make_settings(top_k=3, relevance_floor=0.45)
