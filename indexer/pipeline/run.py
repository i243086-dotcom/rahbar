"""The indexer Job's entry point. It runs once and exits (section 4.2).

    python -m pipeline.run --dummy    # week 1: three fake chunks, no model needed
    python -m pipeline.run            # the real pipeline: extract, clean, chunk, embed, store
    python -m pipeline.run --dry-run --dump chunks.jsonl   # no model, no Chroma: inspect chunks

Exit code 0 means the index was written; anything else fails the Job, and
Kubernetes retries it up to the Job's backoffLimit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .config import IndexerSettings, get_settings
from .models import Chunk


def log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer", "msg": msg, **fields}), flush=True)


def _front_matter(path: Path) -> dict[str, str]:
    """Read `key: value` lines between leading '---' markers (used by eval/fixtures)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def discover(corpus_dir: str) -> list[tuple[Path, str, bool]]:
    """List (path, doc_version, superseded) for every document to index.

    corpus/fetch.py writes _index.json next to the files it downloads; use it when
    present. Otherwise read Markdown front matter (the CI fixtures work this way).
    """
    root = Path(corpus_dir)
    index = root / "_index.json"
    if index.exists():
        entries = json.loads(index.read_text(encoding="utf-8"))
        return [(root / e["file"], str(e.get("doc_version", "unknown")),
                 bool(e.get("superseded", False))) for e in entries]
    found = []
    for path in sorted(root.glob("*")):
        if path.suffix.lower() not in {".pdf", ".md", ".html", ".txt"}:
            continue
        if path.name.lower().startswith("readme"):
            continue
        meta = _front_matter(path) if path.suffix.lower() == ".md" else {}
        found.append((path, meta.get("doc_version", "unknown"),
                      meta.get("superseded", "false").lower() == "true"))
    return found


def build_chunks(settings: IndexerSettings) -> tuple[list[Chunk], dict[str, object]]:
    """Stages 1 to 3 over every document. A document that fails to extract is logged and
    skipped (one bad PDF must not stop the other nine), and listed in the summary."""
    from .chunk import chunk, count_words
    from .clean import clean
    from .extract import extract

    documents = discover(settings.corpus_dir)
    if not documents:
        raise SystemExit(f"no documents found in {settings.corpus_dir}")
    all_chunks: list[Chunk] = []
    skipped: list[str] = []
    original_words = 0
    ocr_pages = 0
    for path, doc_version, superseded in documents:
        try:
            doc = clean(extract(str(path), doc_version, superseded, skip_ocr=settings.skip_ocr))
            pieces = chunk(doc, settings.chunk_size, settings.chunk_overlap,
                           mode=settings.chunk_mode)
        except Exception as exc:
            log("document skipped", source=path.name, error=repr(exc))
            skipped.append(path.name)
            continue
        original_words += sum(count_words(p.text) for p in doc.pages)
        ocr_pages += sum(1 for p in doc.pages if p.ocr)
        log("chunked", source=path.name, chunks=len(pieces), doc_version=doc_version,
            superseded=superseded)
        all_chunks.extend(pieces)
    if not all_chunks:
        raise SystemExit("every document failed; keeping the old index")
    stored_words = sum(count_words(c.text) for c in all_chunks)
    summary: dict[str, object] = {
        "documents": len(documents) - len(skipped), "skipped": skipped, "ocr_pages": ocr_pages,
        "chunks": len(all_chunks), "original_words": original_words,
        "stored_words": stored_words,
        "storage_amplification": round(stored_words / max(original_words, 1), 3),
    }
    return all_chunks, summary


def run_pipeline(settings: IndexerSettings) -> int:
    from .cache import invalidate_cache
    from .embed import embed
    from .store import store

    all_chunks, summary = build_chunks(settings)
    log("chunking summary", **summary)
    vectors = embed([c.text for c in all_chunks], settings)
    log("embedded", vectors=len(vectors), dimension=len(vectors[0]), model=settings.embed_model)
    count = store(all_chunks, vectors, settings)
    expired = invalidate_cache(settings)
    log("cache invalidated", keys_removed=expired)
    return count


def dry_run(settings: IndexerSettings, dump: str | None) -> int:
    """Extract, clean and chunk only: no embeddings, no Chroma. Writes one JSON object per
    chunk to `dump`. Used to write the golden set (sections), to inspect OCR and tables,
    and by eval/chunk_experiment.py."""
    chunks, summary = build_chunks(settings)
    log("dry run", **summary)
    if dump:
        with open(dump, "w", encoding="utf-8") as fh:
            for c in chunks:
                fh.write(json.dumps({"id": c.id, "text": c.text, **c.metadata()}) + "\n")
        log("chunks written", path=dump)
    return len(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the RAHBAR index, then exit.")
    parser.add_argument("--dummy", action="store_true", help="write three fake chunks")
    parser.add_argument("--dry-run", action="store_true",
                        help="extract, clean and chunk only; no model, no Chroma")
    parser.add_argument("--dump", metavar="FILE", help="with --dry-run: write chunks as JSONL")
    args = parser.parse_args()
    settings = get_settings()
    log("indexer starting", dummy=args.dummy, embed_model=settings.embed_model,
        collection=settings.collection, chroma=f"{settings.chroma_host}:{settings.chroma_port}",
        pod=os.environ.get("HOSTNAME", "-"))
    started = time.perf_counter()
    try:
        if args.dry_run:
            count = dry_run(settings, args.dump)
        elif args.dummy:
            from .dummy import write_dummy_index
            from .store import get_client

            count = write_dummy_index(settings, get_client(settings))
        else:
            count = run_pipeline(settings)
    except NotImplementedError as exc:
        log("indexer stage not implemented yet", error=str(exc))
        return 2
    log("indexer finished", chunks=count, seconds=round(time.perf_counter() - started, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
