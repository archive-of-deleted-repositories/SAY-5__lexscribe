from __future__ import annotations

from lexscribe_worker.tasks import classify_spans, run_pipeline_sync, schedule_for


def test_full_pipeline_classifies_known_clauses() -> None:
    pages = [
        (1, "This Agreement shall terminate on Change of Control of the parties."),
        (2, "All Intellectual Property created hereunder vests in Customer."),
        (3, "This Agreement shall be governed by the laws of Delaware."),
    ]
    out = run_pipeline_sync("doc_x", 1, pages)
    labels = {s["clause_type"] for s in out["spans"]}
    assert "change_of_control" in labels
    assert "ip_assignment" in labels
    assert "governing_law" in labels


def test_classify_handles_no_chunks() -> None:
    out = classify_spans.run(  # type: ignore[attr-defined]
        {"doc_id": "doc_x", "version": 1, "chunks": []}
    )
    assert out["spans"] == []


def test_schedule_matches_default_delays() -> None:
    assert schedule_for(5) == [1.0, 4.0, 16.0, 64.0]
