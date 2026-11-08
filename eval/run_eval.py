#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.

Given: talking to the API, reading the golden set, writing results.json, the exit
code. Yours (done): recall_at_k, citation_validity, summarise and gate. They are the evaluation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def section_matches(a: str, b: str) -> bool:
    """Equal, or one is the other's numbered prefix at a clean boundary: "5.4" matches
    "5.4 Academic Warning", but "1.2" does not match "1.21". Same rule as
    api/app/services/citations.py, so a golden `section` can be written as just the number."""
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if not short or not long_.startswith(short):
        return False
    nxt = long_[len(short)]
    if nxt.isalnum():
        return False
    return not (nxt == "." and long_[len(short) + 1:len(short) + 2].isdigit())


def _matches(rel: dict, got: dict) -> bool:
    """A golden entry is {chunk_id} or {source, section}. Sources compare case-insensitively."""
    if rel.get("chunk_id"):
        return rel["chunk_id"] == got.get("chunk_id")
    return (_norm(rel.get("source", "")) == _norm(got.get("source", ""))
            and section_matches(rel.get("section", ""), got.get("section", "")))


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions).

    Matching: by source (case-insensitive) and section (equal, or a numbered prefix at a clean
    boundary), or by chunk_id when the golden entry gives one. Several retrieved chunks from
    the same section count once, because the golden set lists sections, not chunks."""
    if not relevant:
        return None
    top = retrieved[:k]
    found = sum(1 for rel in relevant if any(_matches(rel, got) for got in top))
    return found / len(relevant)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations."""
    citations = response.get("citations") or []
    if not citations:
        return None
    retrieved = response.get("retrieved") or []
    valid = sum(1 for c in citations if any(_matches(c, got) for got in retrieved))
    return valid / len(citations)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json."""
    r3: list[float] = []
    r5: list[float] = []
    by_type: dict[str, dict[str, list[float]]] = {}
    cite_valid = cite_total = dropped = 0
    abstain_ok: list[float] = []
    top1_answerable: list[float] = []
    top1_abstain: list[float] = []
    injection_ok: list[float] = []
    for row in rows:
        resp, kind = row["response"], row["type"]
        retrieved = resp.get("retrieved") or []
        a3 = recall_at_k(row["relevant"], retrieved, 3)
        a5 = recall_at_k(row["relevant"], retrieved, 5)
        if a5 is not None and a3 is not None:
            r3.append(a3)
            r5.append(a5)
            bucket = by_type.setdefault(kind, {"r3": [], "r5": []})
            bucket["r3"].append(a3)
            bucket["r5"].append(a5)
        citations = resp.get("citations") or []
        cite_total += len(citations)
        cite_valid += sum(1 for c in citations
                          if any(_matches(c, got) for got in retrieved))
        dropped += int(resp.get("citations_dropped", 0))
        top1 = retrieved[0]["score"] if retrieved else None
        if row["must_abstain"]:
            abstain_ok.append(0.0 if resp.get("answered_from_context") else 1.0)
            if top1 is not None:
                top1_abstain.append(top1)
        elif top1 is not None:
            top1_answerable.append(top1)
        if kind == "injection" and row.get("expect"):
            held = bool(resp.get("answered_from_context")) and \
                str(row["expect"]).lower() in str(resp.get("answer", "")).lower()
            injection_ok.append(1.0 if held else 0.0)
    return {
        "recall_at_3": _mean(r3),
        "recall_at_5": _mean(r5),
        "recall_at_3_by_type": {k: _mean(v["r3"]) for k, v in sorted(by_type.items())},
        "recall_at_5_by_type": {k: _mean(v["r5"]) for k, v in sorted(by_type.items())},
        "citation_validity": round(cite_valid / cite_total, 4) if cite_total else None,
        "citations_total": cite_total,
        "citations_dropped_by_api": dropped,   # fabricated citations the API caught before returning
        "abstention_correctness": _mean(abstain_ok),
        "injection_resisted": _mean(injection_ok),
        # Use these two to choose RELEVANCE_FLOOR: it belongs between them.
        "min_top1_score_answerable": round(min(top1_answerable), 4) if top1_answerable else None,
        "max_top1_score_must_abstain": round(max(top1_abstain), 4) if top1_abstain else None,
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures: list[str] = []
    recall5 = results.get("recall_at_5")
    if baseline and baseline.get("recall_at_5") is not None and recall5 is not None:
        drop = baseline["recall_at_5"] - recall5
        if drop > MAX_RECALL5_DROP + 1e-9:
            failures.append(f"recall@5 fell {drop * 100:.1f} points below the baseline "
                            f"({recall5:.3f} vs {baseline['recall_at_5']:.3f}; "
                            f"limit {MAX_RECALL5_DROP * 100:.0f})")
    abstention = results.get("abstention_correctness")
    if abstention is not None and abstention < REQUIRED_ABSTENTION:
        failures.append("a must-abstain question was answered from context "
                        f"(abstention correctness {abstention:.2f}, required 1.00)")
    validity = results.get("citation_validity")
    if validity is not None and validity < MIN_CITATION_VALIDITY:
        failures.append(f"citation validity {validity:.3f} is below {MIN_CITATION_VALIDITY}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=900.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            try:
                response = ask(client, args.api, q["question"])
            except httpx.HTTPError as exc:   # one slow or failed question must not lose the run
                print(f"  {q['id']:<5} FAILED: {exc!r}")
                response = {"request_id": "-", "answer": "", "citations": [],
                            "answered_from_context": False, "confidence": "low",
                            "retrieved": [], "provider": "eval-error"}
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    try:
        results = summarise(rows)
        baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
        failures = gate(results, baseline)
    except NotImplementedError as exc:
        print(f"\nnot implemented yet: {exc}")
        return 2

    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    print(f"  recall@3={results['recall_at_3']}  recall@5={results['recall_at_5']}  "
          f"citation_validity={results['citation_validity']}  "
          f"abstention={results['abstention_correctness']}  "
          f"injection_resisted={results['injection_resisted']}")
    print(f"  recall@5 by type: {results['recall_at_5_by_type']}")
    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
