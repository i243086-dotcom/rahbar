"""Unit tests for eval/run_eval.py: the metrics and the CI gate (section 5)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "run_eval", Path(__file__).resolve().parents[2] / "eval" / "run_eval.py")
assert spec and spec.loader
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def ref(source: str, section: str, cid: str = "x", score: float = 0.8) -> dict:
    return {"chunk_id": cid, "source": source, "section": section, "page": 1, "score": score}


REL = [{"source": "r.md", "section": "5.4"}, {"source": "r.md", "section": "1. Attendance"}]


def test_recall_counts_relevant_sections_found_in_the_top_k() -> None:
    got = [ref("r.md", "9. Other"), ref("r.md", "5.4 Academic Warning"), ref("r.md", "1. Attendance")]
    assert ev.recall_at_k(REL, got, 3) == 1.0
    assert ev.recall_at_k(REL, got, 2) == 0.5
    assert ev.recall_at_k([], got, 3) is None            # must-abstain: no relevant passages


def test_recall_section_prefix_has_a_clean_boundary() -> None:
    assert ev.recall_at_k([{"source": "r.md", "section": "1.2"}], [ref("r.md", "1.21 Attendance")], 5) == 0.0


def test_recall_can_match_by_chunk_id() -> None:
    assert ev.recall_at_k([{"chunk_id": "c9"}], [ref("a", "b", cid="c9")], 5) == 1.0


def test_citation_validity_checks_every_citation_against_retrieved() -> None:
    resp = {"retrieved": [ref("r.md", "1. Attendance")],
            "citations": [{"source": "r.md", "section": "1. Attendance", "page": 1},
                          {"source": "ghost.pdf", "section": "7", "page": 1}]}
    assert ev.citation_validity(resp) == 0.5
    assert ev.citation_validity({"retrieved": [], "citations": []}) is None


def row(kind: str, relevant: list, answered: bool, retrieved: list, must_abstain: bool = False,
        answer: str = "", expect: str | None = None, citations: list | None = None) -> dict:
    return {"id": "q", "type": kind, "must_abstain": must_abstain, "relevant": relevant,
            "expect": expect, "seconds": 0.1,
            "response": {"retrieved": retrieved, "answered_from_context": answered,
                         "answer": answer, "citations": citations or []}}


def test_summarise_breaks_recall_down_by_type_and_scores_abstention() -> None:
    rows = [
        row("ordinary", [REL[0]], True, [ref("r.md", "5.4 Academic Warning", score=0.7)]),
        row("exact", [REL[1]], True, [ref("r.md", "Wrong", score=0.6)]),
        row("abstain", [], False, [ref("r.md", "x", score=0.3)], must_abstain=True),
        row("injection", [], True, [], answer="You need 80 percent.", expect="80"),
    ]
    out = ev.summarise(rows)
    assert out["recall_at_5"] == 0.5
    assert out["recall_at_5_by_type"] == {"exact": 0.0, "ordinary": 1.0}
    assert out["abstention_correctness"] == 1.0 and out["injection_resisted"] == 1.0
    assert out["max_top1_score_must_abstain"] == 0.3 and out["min_top1_score_answerable"] == 0.6


def test_gate_passes_on_equal_or_small_drop_and_fails_on_the_three_conditions() -> None:
    base = {"recall_at_5": 0.80}
    ok = {"recall_at_5": 0.76, "abstention_correctness": 1.0, "citation_validity": 1.0}
    assert ev.gate(ok, base) == []
    assert any("recall@5" in m for m in ev.gate({**ok, "recall_at_5": 0.70}, base))
    assert any("must-abstain" in m for m in ev.gate({**ok, "abstention_correctness": 0.5}, base))
    assert any("citation validity" in m for m in ev.gate({**ok, "citation_validity": 0.9}, base))
    assert ev.gate(ok, None) == []                       # first run: no baseline yet
