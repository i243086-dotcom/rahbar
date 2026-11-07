#!/usr/bin/env python3
"""Check eval/golden.yaml against section 5.1, and against what your indexer really produces.

    python -m pipeline.run --dry-run --dump chunks.jsonl        # from indexer/, CORPUS_DIR set
    python eval/validate_golden.py --dump indexer/chunks.jsonl
    python eval/validate_golden.py --dump chunks.jsonl --grep "attendance"   # find sections

The golden set must be written BEFORE you tune anything, from the documents, not from what
your retriever returns. This script only checks that each `relevant` (source, section) names a
chunk that exists, so a typo cannot silently score as a retrieval miss.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_eval import _matches  # noqa: E402

MINIMUM = {"ordinary": 8, "version": 2, "exact": 2, "abstain": 2, "injection": 1}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    ap.add_argument("--dump", type=Path, help="chunks.jsonl from `pipeline.run --dry-run --dump`")
    ap.add_argument("--grep", help="list chunk sections whose text contains this word")
    args = ap.parse_args()

    chunks = []
    if args.dump:
        chunks = [json.loads(line) for line in args.dump.read_text(encoding="utf-8").splitlines()]
    if args.grep:
        seen = set()
        for c in chunks:
            if args.grep.lower() in c["text"].lower() and (c["source"], c["section"]) not in seen:
                seen.add((c["source"], c["section"]))
                print(f"{c['source']:<45} {c['section']!r:<50} v={c['doc_version']} "
                      f"superseded={c['superseded']} p{c['page']}")
        return 0

    questions = yaml.safe_load(args.golden.read_text(encoding="utf-8")).get("questions") or []
    problems: list[str] = []
    counts = Counter(q.get("type", "ordinary") for q in questions)
    if len(questions) < 15:
        problems.append(f"{len(questions)} questions; 15 are required")
    for kind, need in MINIMUM.items():
        if counts[kind] < need:
            problems.append(f"type {kind!r}: {counts[kind]} questions, need {need}")
    ids = [q.get("id") for q in questions]
    if len(set(ids)) != len(ids):
        problems.append("duplicate question ids")
    for q in questions:
        qid = q.get("id", "?")
        text = str(q.get("question", ""))
        if "TODO" in text.upper() or len(text) < 10:
            problems.append(f"{qid}: question text is still a placeholder")
        must = bool(q.get("must_abstain"))
        rel = q.get("relevant") or []
        if must and rel:
            problems.append(f"{qid}: a must-abstain question must have no relevant passages")
        if not must and not rel:
            problems.append(f"{qid}: no `relevant` passages (only must-abstain questions may be empty)")
        if chunks:
            for r in rel:
                if not any(_matches(r, c) for c in chunks):
                    problems.append(f"{qid}: relevant {r} matches no chunk in {args.dump}")
    print(f"{len(questions)} questions: {dict(counts)}")
    for p in problems:
        print(f"  PROBLEM  {p}")
    print("golden set OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
