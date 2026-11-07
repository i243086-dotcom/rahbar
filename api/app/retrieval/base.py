"""The retriever interface. The rest of the API only ever sees this."""

from __future__ import annotations

from typing import Protocol

from ..schemas import Passage


class Retriever(Protocol):
    name: str

    def embed_query(self, question: str) -> list[float] | None:
        """The question's vector, or None when this retriever does not use vectors."""
        ...

    def scope(self, question: str) -> str:
        """"current" (superseded documents excluded) or "all" (the user asked about an older
        version). The cache keys on it, so a current answer is never served for an old one."""
        ...

    def index_id(self) -> str:
        """Identifies the index build the answers come from; changes on every re-index."""
        ...

    def retrieve(
        self, question: str, k: int, query_vector: list[float] | None = None
    ) -> list[Passage]:
        """Return up to k passages, best first."""
        ...
