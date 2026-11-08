from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from pipeline.chunk import chunk, count_words
from pipeline.config import IndexerSettings, get_settings
from pipeline.embed import embed
from pipeline.extract import extract
from pipeline.clean import clean
from pipeline.models import Chunk, Document, Page
from pipeline.run import build_chunks
from pipeline.store import store

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def doc_from(text: str, version: str = "2026", superseded: bool = False) -> Document:
    return Document("rules.md", version, superseded, [Page("rules.md", 1, text)])


# ----------------------------------------------------------------------------- chunking
def test_every_chunk_carries_the_required_metadata_and_its_heading() -> None:
    doc = clean(extract(str(FIXTURES / "academic-rules-2023.md"), "2023", True))
    chunks = chunk(doc, 400, 50)
    sections = {c.section for c in chunks}
    assert "1. Attendance" in sections and "2. Academic warning" in sections
    for c in chunks:
        assert c.doc_version == "2023" and c.superseded is True
        assert c.text.startswith(c.section) or c.section == "(front matter)"
        assert set(c.metadata()) == {"source", "section", "page", "doc_version", "superseded"}


def test_chunks_respect_the_size_budget_and_ids_are_stable() -> None:
    body = " ".join(f"Sentence number {i} says something useful." for i in range(120))
    doc = doc_from(f"# Rules\n\n## 1. Long section\n\n{body}")
    first, second = chunk(doc, 60, 10), chunk(doc, 60, 10)
    assert [c.id for c in first] == [c.id for c in second]          # stable ids
    assert len({c.id for c in first}) == len(first)                 # unique ids
    assert len(first) > 3
    assert all(count_words(c.text) <= 60 + 2 for c in first)        # + heading rounding


def test_overlap_is_shared_between_neighbours_inside_a_section() -> None:
    body = " ".join(f"Sentence number {i} is here." for i in range(60))
    doc = doc_from(f"## 1. Long section\n\n{body}")
    chunks = chunk(doc, 50, 12)
    a, b = chunks[0].text.split(), chunks[1].text.split()
    assert set(a[-12:]) & set(b[:20])                               # tail of one starts the next


def test_overlap_never_crosses_a_section_boundary() -> None:
    doc = doc_from("## 1. Alpha\n\nAlpha text one. Alpha text two.\n\n## 2. Beta\n\nBeta text.")
    chunks = chunk(doc, 400, 50)
    beta = next(c for c in chunks if c.section == "2. Beta")
    assert "Alpha" not in beta.text


def test_table_is_split_by_rows_with_its_header_repeated() -> None:
    rows = "\n".join(f"| Charge {i} | {1000 + i} |" for i in range(40))
    doc = doc_from(f"## 2. Fees\n\n| Charge | Amount |\n| --- | --- |\n{rows}")
    chunks = chunk(doc, 60, 5)
    assert len(chunks) > 1
    assert all("| Charge | Amount |" in c.text for c in chunks)


def test_a_clause_is_not_mistaken_for_a_heading() -> None:
    doc = doc_from("## 1. Attendance\n\n1.1 A student must attend at least 80 percent of lectures.")
    assert {c.section for c in chunk(doc, 400, 50)} == {"1. Attendance"}


def test_fixed_mode_cuts_across_sections_and_ignores_overlap_setting_zero() -> None:
    doc = doc_from("## 1. A\n\n" + "alpha " * 30 + "\n\n## 2. B\n\n" + "beta " * 30)
    chunks = chunk(doc, 20, 0, mode="fixed")
    assert any("alpha" in c.text and "beta" in c.text for c in chunks)


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError):
        chunk(doc_from("text"), 50, 50)


# ----------------------------------------------------------------------------- embedding
def mock_client(vector_for: Any = None, wrong_count: bool = False) -> httpx.Client:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        n = len(body["input"]) - (1 if wrong_count else 0)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]] * n})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.seen = seen  # type: ignore[attr-defined]
    return client


def test_embed_batches_and_uses_the_pinned_model_with_document_prefix() -> None:
    settings = get_settings()
    client = mock_client()
    vectors = embed([f"t{i}" for i in range(40)], settings, client)
    assert len(vectors) == 40 and len(vectors[0]) == 3
    calls = client.seen  # type: ignore[attr-defined]
    assert len(calls) == 3                                           # 16 + 16 + 8
    assert all(c["model"] == settings.embed_model for c in calls)
    assert calls[0]["input"][0].startswith("search_document: ")


def test_embed_fails_loudly_when_the_server_drops_a_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipeline.embed.time.sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        embed(["a", "b"], get_settings(), mock_client(wrong_count=True))


# ----------------------------------------------------------------------------- store
class FakeCollection:
    def __init__(self, client: "FakeClient", name: str, metadata: dict[str, Any]) -> None:
        self.client, self.name, self.metadata, self.rows = client, name, metadata, {}

    def add(self, ids: list[str], documents: list[str], embeddings: Any, metadatas: Any) -> None:
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def count(self) -> int:
        return len(self.rows)

    def modify(self, name: str) -> None:
        self.client.collections.pop(self.name)
        self.name = name
        self.client.collections[name] = self


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise ValueError("no such collection")
        del self.collections[name]

    def create_collection(self, name: str, metadata: dict[str, Any]) -> FakeCollection:
        self.collections[name] = FakeCollection(self, name, metadata)
        return self.collections[name]


def sample_chunks(n: int = 3, superseded: bool = False) -> list[Chunk]:
    return [Chunk(f"c{i}", f"text {i}", "a.pdf", f"{i} Sec", 1, "2023", superseded)
            for i in range(n)]


def test_store_records_the_pin_and_swaps_atomically() -> None:
    client = FakeClient()
    settings = get_settings()
    old = client.create_collection(settings.collection, {"embed_model": "old"})
    old.add(["x"], ["old"], [[0.0]], [{}])
    assert store(sample_chunks(), [[0.1, 0.2]] * 3, settings, client) == 3
    live = client.collections[settings.collection]
    assert live.metadata["embed_model"] == settings.embed_model       # the pin
    assert live.metadata["dimension"] == 2
    assert live.metadata["index_id"] and live.count() == 3
    assert f"{settings.collection}__build" not in client.collections  # temp name is gone


def test_store_records_superseded_versions_for_the_api() -> None:
    client = FakeClient()
    store(sample_chunks(superseded=True), [[0.1]] * 3, get_settings(), client)
    assert client.collections[get_settings().collection].metadata["superseded_versions"] == "2023"


def test_store_never_replaces_a_live_index_with_nothing() -> None:
    client = FakeClient()
    live = client.create_collection(get_settings().collection, {})
    live.add(["x"], ["old"], [[0.0]], [{}])
    with pytest.raises(ValueError):
        store([], [], get_settings(), client)
    assert client.collections[get_settings().collection].count() == 1


def test_a_failed_write_keeps_the_old_index() -> None:
    class Broken(FakeCollection):
        def add(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("chroma went away")

    client = FakeClient()
    settings = get_settings()
    old = client.create_collection(settings.collection, {})
    old.add(["x"], ["old"], [[0.0]], [{}])
    client.create_collection = lambda name, metadata: Broken(client, name, metadata)  # type: ignore
    with pytest.raises(RuntimeError):
        store(sample_chunks(), [[0.1]] * 3, settings, client)
    assert client.collections[settings.collection].count() == 1       # old index untouched


def test_store_rejects_duplicate_ids_and_length_mismatch() -> None:
    with pytest.raises(ValueError):
        store(sample_chunks() + sample_chunks(1), [[0.1]] * 4, get_settings(), FakeClient())
    with pytest.raises(ValueError):
        store(sample_chunks(), [[0.1]], get_settings(), FakeClient())


# ----------------------------------------------------------------------------- the whole front half
def test_build_chunks_over_the_fixture_corpus_reports_the_summary() -> None:
    base = get_settings()
    settings = IndexerSettings(**{**base.__dict__, "corpus_dir": str(FIXTURES)})
    chunks, summary = build_chunks(settings)
    assert summary["documents"] == 3 and summary["skipped"] == []
    assert {c.superseded for c in chunks} == {True, False}
    assert any(c.source == "academic-rules-2023.md" and c.superseded for c in chunks)
    assert summary["storage_amplification"] > 0


def test_a_bad_document_is_skipped_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "good.md").write_text("## 1. Ok\n\nSome real text here.", encoding="utf-8")
    (tmp_path / "bad.pdf").write_bytes(b"this is not a pdf")
    base = get_settings()
    settings = IndexerSettings(**{**base.__dict__, "corpus_dir": str(tmp_path)})
    chunks, summary = build_chunks(settings)
    assert summary["skipped"] == ["bad.pdf"] and len(chunks) == 1
