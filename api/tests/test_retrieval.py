from __future__ import annotations

from typing import Any

from app.config import Settings
from app.retrieval.chroma import ChromaRetriever
from app.retrieval.exact import contains_term, exact_terms
from app.retrieval.versions import wants_older

from .conftest import make_settings


class FakeCollection:
    """Answers query() from a list of rows, honouring `where` and `where_document`."""

    def __init__(self, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
        self.rows, self.metadata, self.queries = rows, metadata, []

    def count(self) -> int:
        return len(self.rows)

    def query(self, query_embeddings: Any, n_results: int, include: Any, where: Any = None,
              where_document: Any = None) -> dict[str, Any]:
        self.queries.append({"where": where, "where_document": where_document})
        rows = self.rows
        if where:
            rows = [r for r in rows if r["meta"]["superseded"] == where["superseded"]]
        if where_document:
            term = where_document["$contains"]
            rows = [r for r in rows if term in r["text"]]
        rows = sorted(rows, key=lambda r: r["distance"])[:n_results]
        return {"ids": [[r["id"] for r in rows]], "documents": [[r["text"] for r in rows]],
                "metadatas": [[r["meta"] for r in rows]],
                "distances": [[r["distance"] for r in rows]]}


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def get_collection(self, name: str) -> FakeCollection:
        return self.collection


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


def row(i: str, text: str, distance: float, superseded: bool = False, version: str = "2026") -> dict:
    return {"id": i, "text": text, "distance": distance,
            "meta": {"source": "rules.md", "section": f"S{i}", "page": 1,
                     "doc_version": version, "superseded": superseded}}


def retriever(rows: list[dict[str, Any]], **settings: Any) -> tuple[ChromaRetriever, FakeCollection]:
    col = FakeCollection(rows, {"index_id": "abc", "superseded_versions": "2023"})
    s: Settings = make_settings(retriever="chroma", **settings)
    return ChromaRetriever(s, embedder=FakeEmbedder(), client=FakeClient(col)), col


def test_distance_is_converted_to_similarity_and_sorted() -> None:
    r, _ = retriever([row("a", "x", 0.4), row("b", "y", 0.1)])
    out = r.retrieve("anything", 2)
    assert [p.chunk_id for p in out] == ["b", "a"]
    assert out[0].score == 0.9


def test_superseded_documents_are_filtered_out_by_default() -> None:
    r, col = retriever([row("old", "75 percent", 0.05, superseded=True, version="2023"),
                        row("new", "80 percent", 0.20)])
    out = r.retrieve("What is the attendance requirement?", 5)
    assert [p.chunk_id for p in out] == ["new"]
    assert col.queries[0]["where"] == {"superseded": False}


def test_asking_about_an_older_version_lifts_the_filter() -> None:
    r, _ = retriever([row("old", "75 percent", 0.05, superseded=True, version="2023"),
                      row("new", "80 percent", 0.20)])
    assert r.scope("What was the attendance rule in 2023?") == "all"
    assert r.scope("What was the previous attendance rule?") == "all"
    assert {p.chunk_id for p in r.retrieve("What was the rule in 2023?", 5)} == {"old", "new"}


def test_failure_switch_removes_the_version_filter() -> None:
    """Stage E of the failure analysis: INCLUDE_SUPERSEDED=true."""
    r, _ = retriever([row("old", "75", 0.05, superseded=True, version="2023")],
                     include_superseded=True)
    assert r.retrieve("What is the attendance requirement?", 5)[0].superseded is True


def test_exact_term_search_rescues_a_chunk_the_vectors_ranked_low() -> None:
    far = row("clause", "1.21 Attendance is compulsory.", 0.9)          # similarity 0.10
    near = [row(str(i), f"general text {i}", 0.1 + i / 100) for i in range(8)]
    r, col = retriever(near + [far], fetch_k=5, exact_boost=0.1)
    out = r.retrieve("What does clause 1.21 require?", 3)
    assert "clause" in [p.chunk_id for p in out]
    hit = next(p for p in out if p.chunk_id == "clause")
    assert hit.exact_match is True
    assert any(q["where_document"] == {"$contains": "1.21"} for q in col.queries)


def test_index_id_and_info_come_from_collection_metadata() -> None:
    r, _ = retriever([row("a", "x", 0.1)])
    assert r.index_id() == "abc"
    assert r.info().count == 1


def test_exact_terms_extracts_clauses_codes_amounts_percentages() -> None:
    q = "Does CS-1002 clause 1.21 cost 10,000 or need 80%?"
    assert set(exact_terms(q)) == {"1.21", "CS-1002", "10,000"}          # capped at three
    assert contains_term("Fee is 10,000 PKR", ["10,000"])
    assert exact_terms("What is the attendance requirement?") == []


def test_wants_older_by_word_or_by_year_of_a_superseded_document() -> None:
    assert wants_older("what did the old policy say", [])
    assert wants_older("rules in 2023", ["2023-08"])
    assert not wants_older("rules in 2026", ["2023-08"])
    assert not wants_older("What is the attendance requirement?", ["2023-08"])
