#!/usr/bin/env python3
"""Measure recall@3 / recall@5 for several (size, overlap) settings (section 3.1).

    python eval/chunk_experiment.py --corpus corpus/raw --golden eval/golden.yaml \\
        --configs 200:25,400:50,800:100            # needs Ollama running (nomic-embed-text)
    python eval/chunk_experiment.py --corpus eval/fixtures --golden eval/fixtures/golden.fixture.yaml \\
        --embedder hash                            # no model: a bag-of-words stand-in, for tests

It extracts and cleans each document once, then for every setting chunks, embeds, searches in
memory (cosine, superseded documents excluded, like the API) and scores the golden questions
with the same recall_at_k as run_eval.py. The printed table goes into docs/PIPELINE.md.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "indexer"))
sys.path.insert(0, str(HERE))

from run_eval import recall_at_k  # noqa: E402


def hash_embed(texts: list[str], dim: int = 512) -> list[list[float]]:
    """A deterministic bag-of-words embedding. Not a real model: it only makes the experiment
    runnable offline (CI, tests). Your reported numbers must come from the real model."""
    out = []
    for text in texts:
        v = [0.0] * dim
        for tok in re.findall(r"[a-z0-9.]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def run(corpus: str, golden: Path, configs: list[tuple[int, int]], embedder: str,
        ollama_url: str, model: str) -> list[dict]:
    from pipeline.chunk import chunk, count_words
    from pipeline.clean import clean
    from pipeline.config import IndexerSettings, get_settings
    from pipeline.embed import embed
    from pipeline.extract import extract
    from pipeline.run import discover

    base = get_settings()
    settings = IndexerSettings(**{**base.__dict__, "corpus_dir": corpus, "ollama_url": ollama_url,
                                  "embed_model": model})
    questions = [q for q in yaml.safe_load(golden.read_text(encoding="utf-8"))["questions"]
                 if q.get("relevant") and not q.get("must_abstain")]
    if not questions:
        sys.exit("the golden set has no answerable questions with `relevant` filled in")

    def embed_docs(texts: list[str]) -> list[list[float]]:
        return hash_embed(texts) if embedder == "hash" else embed(texts, settings)

    docs = []
    for path, version, superseded in discover(corpus):
        try:
            docs.append(clean(extract(str(path), version, superseded)))
        except Exception as exc:  # noqa: BLE001
            print(f"skipped {path.name}: {exc!r}", file=sys.stderr)
    original = sum(count_words(p.text) for d in docs for p in d.pages)

    results = []
    for size, overlap in configs:
        chunks = [c for d in docs for c in chunk(d, size, overlap)]
        vectors = embed_docs([c.text for c in chunks])
        live = [(c, v) for c, v in zip(chunks, vectors, strict=True) if not c.superseded]
        if embedder == "hash":
            qvecs = hash_embed([q["question"] for q in questions])
        else:
            import httpx
            prefix = "search_query: " if model.startswith("nomic-embed-text") else ""
            r = httpx.post(f"{ollama_url.rstrip('/')}/api/embed", timeout=300,
                           json={"model": model,
                                 "input": [prefix + q["question"] for q in questions]})
            r.raise_for_status()
            qvecs = r.json()["embeddings"]
        r3: list[float] = []
        r5: list[float] = []
        by_type: dict[str, list[float]] = {}
        for q, qv in zip(questions, qvecs, strict=True):
            ranked = sorted(live, key=lambda cv: cosine(qv, cv[1]), reverse=True)[:5]
            got = [{"chunk_id": c.id, "source": c.source, "section": c.section} for c, _ in ranked]
            a3, a5 = recall_at_k(q["relevant"], got, 3), recall_at_k(q["relevant"], got, 5)
            assert a3 is not None and a5 is not None
            r3.append(a3)
            r5.append(a5)
            by_type.setdefault(q.get("type", "ordinary"), []).append(a5)
        stored = sum(count_words(c.text) for c in chunks)
        results.append({
            "size": size, "overlap": overlap, "chunks": len(chunks),
            "amplification": round(stored / max(original, 1), 2),
            "recall3": round(sum(r3) / len(r3), 3), "recall5": round(sum(r5) / len(r5), 3),
            "by_type": {k: round(sum(v) / len(v), 2) for k, v in sorted(by_type.items())},
        })
    return results


def to_markdown(results: list[dict]) -> str:
    lines = ["| Size (words) | Overlap (words) | recall@3 | recall@5 | Chunks stored | "
             "Amplification | recall@5 by type |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        by = ", ".join(f"{k} {v}" for k, v in r["by_type"].items())
        lines.append(f"| {r['size']} | {r['overlap']} | {r['recall3']} | {r['recall5']} | "
                     f"{r['chunks']} | {r['amplification']} | {by} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    ap.add_argument("--configs", default="200:25,400:50,800:100", help="size:overlap,size:overlap")
    ap.add_argument("--embedder", choices=["ollama", "hash"], default="ollama")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--model", default="nomic-embed-text")
    args = ap.parse_args()
    configs = [tuple(int(x) for x in c.split(":")) for c in args.configs.split(",")]
    print(to_markdown(run(args.corpus, args.golden, configs, args.embedder,  # type: ignore[arg-type]
                          args.ollama_url, args.model)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
