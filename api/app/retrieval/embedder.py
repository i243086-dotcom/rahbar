"""Embeds the user's question with the SAME model the indexer used (section 3.2, step 3).

Always goes through Ollama at OLLAMA_URL, whichever LLM_PROVIDER generates the answer:
the pinned embedding model has to be the one that built the index.
"""

from __future__ import annotations

import httpx

from ..config import Settings

QUERY_PREFIX = "search_query: "     # pairs with the indexer's "search_document: "


class EmbeddingError(RuntimeError):
    pass


class OllamaEmbedder:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.model = settings.embed_model
        self.url = settings.ollama_url.rstrip("/")
        self.prefix = QUERY_PREFIX if self.model.startswith("nomic-embed-text") else ""
        self.client = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0))

    def embed_query(self, text: str) -> list[float]:
        try:
            r = self.client.post(f"{self.url}/api/embed",
                                 json={"model": self.model, "input": [self.prefix + text]})
            r.raise_for_status()
            return [float(x) for x in r.json()["embeddings"][0]]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise EmbeddingError(f"could not embed the question with {self.model}: {exc!r}") from exc
