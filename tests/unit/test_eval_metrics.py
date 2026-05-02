from __future__ import annotations

from lexscribe_eval.metrics import score_run


def _row(
    *, doc_id: str, expected_doc: str, answer: str, cited_text: str, cost: float = 0.001
) -> dict:
    return {
        "expected_doc_ids": [expected_doc],
        "answer": answer,
        "citations": [
            {
                "doc_id": doc_id,
                "version": 1,
                "page": 1,
                "char_start": 0,
                "char_end": len(cited_text),
                "score": 0.9,
                "text": cited_text,
            }
        ],
        "usage": {"cost_usd": cost},
        "latency_seconds": 0.1,
    }


def test_score_run_empty_returns_zeros() -> None:
    m = score_run([])
    assert m.n == 0
    assert m.precision_at_1 == 0.0


def test_perfect_run_yields_perfect_precision_and_recall() -> None:
    rows = [
        _row(
            doc_id="doc_a",
            expected_doc="doc_a",
            answer="Delaware governs the agreement.",
            cited_text="This Agreement shall be governed by Delaware law.",
        )
    ]
    m = score_run(rows)
    assert m.precision_at_1 == 1.0
    assert m.recall_at_5 == 1.0


def test_refusal_phrase_counts_as_refusal() -> None:
    rows = [
        _row(
            doc_id="doc_a",
            expected_doc="doc_a",
            answer="I don't know.",
            cited_text="anything",
        )
    ]
    m = score_run(rows)
    assert m.refusal_rate == 1.0


def test_cost_average_is_returned() -> None:
    rows = [
        _row(doc_id="doc_a", expected_doc="doc_a", answer="x", cited_text="y", cost=0.01),
        _row(doc_id="doc_a", expected_doc="doc_a", answer="x", cited_text="y", cost=0.03),
    ]
    m = score_run(rows)
    assert abs(m.cost_usd_avg - 0.02) < 1e-9
