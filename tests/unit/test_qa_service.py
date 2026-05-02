from __future__ import annotations

from lexscribe_api.qa_service import answer_question, default_corpus
from lexscribe_shared.models import QARequest


def test_qa_returns_answer_and_citations() -> None:
    resp = answer_question(QARequest(question="What is the governing law?"), default_corpus())
    assert resp.answer
    assert resp.citations
    assert resp.citations[0].doc_id.startswith("doc_demo")


def test_qa_change_of_control_path() -> None:
    resp = answer_question(QARequest(question="change of control"), default_corpus())
    assert resp.citations
    assert resp.citations[0].page in (1, 2, 3)
    assert resp.usage.tokens_out >= 0


def test_qa_response_includes_model_version() -> None:
    resp = answer_question(QARequest(question="anything"), default_corpus())
    assert resp.model_version
