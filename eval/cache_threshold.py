#!/usr/bin/env python3
"""Choose CACHE_THRESHOLD with data (section 3.3).

The lecture's rule: the lowest threshold with ZERO false hits on your test questions.

    python eval/cache_threshold.py --pairs eval/cache_pairs.yaml          # needs Ollama
    python eval/cache_threshold.py --pairs eval/cache_pairs.yaml --embedder hash   # offline demo

cache_pairs.yaml has two lists of question pairs:
  should_hit:  paraphrases; the second question should be answered from the first's cache entry
  must_miss:   look-alikes with a DIFFERENT answer (another version, programme, number, clause);
               a hit here serves a wrong answer to someone, so it is a false hit.

For each candidate threshold it prints misses (lost savings) and false hits (wrong answers),
then names the lowest threshold with no false hit. Paste the table into docs/PIPELINE.md,
together with the false hit that ruled a lower threshold out.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from chunk_experiment import cosine, hash_embed  # noqa: E402

THRESHOLDS = [0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98]


def embed_pairs(pairs: list[list[str]], embedder: str, url: str, model: str) -> list[float]:
    flat = [q for pair in pairs for q in pair]
    if embedder == "hash":
        vecs = hash_embed(flat)
    else:
        prefix = "search_query: " if model.startswith("nomic-embed-text") else ""
        r = httpx.post(f"{url.rstrip('/')}/api/embed", timeout=300,
                       json={"model": model, "input": [prefix + q for q in flat]})
        r.raise_for_status()
        vecs = r.json()["embeddings"]
    return [cosine(vecs[i], vecs[i + 1]) for i in range(0, len(vecs), 2)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pairs", type=Path, default=HERE / "cache_pairs.yaml")
    ap.add_argument("--embedder", choices=["ollama", "hash"], default="ollama")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--model", default="nomic-embed-text")
    args = ap.parse_args()
    data = yaml.safe_load(args.pairs.read_text(encoding="utf-8"))
    hit_pairs, miss_pairs = data["should_hit"], data["must_miss"]
    hit_sims = embed_pairs(hit_pairs, args.embedder, args.ollama_url, args.model)
    miss_sims = embed_pairs(miss_pairs, args.embedder, args.ollama_url, args.model)

    print("| Threshold | Paraphrases missed | False hits |\n| --- | --- | --- |")
    chosen = None
    for t in THRESHOLDS:
        missed = sum(1 for s in hit_sims if s < t)
        false = [p for p, s in zip(miss_pairs, miss_sims, strict=True) if s >= t]
        print(f"| {t:.2f} | {missed} of {len(hit_sims)} | {len(false)} |")
        if chosen is None and not false:
            chosen = t
    worst = max(zip(miss_sims, miss_pairs, strict=True))
    print(f"\nclosest look-alike pair (similarity {worst[0]:.3f}): {worst[1][0]!r} vs {worst[1][1]!r}")
    print(f"lowest threshold with zero false hits: {chosen}")
    return 0 if chosen is not None else 1


if __name__ == "__main__":
    sys.exit(main())
