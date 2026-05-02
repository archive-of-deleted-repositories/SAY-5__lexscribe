from __future__ import annotations

import pytest
from lexscribe_shared.models import Citation, ClauseType, QARequest
from pydantic import ValidationError as PydanticValidationError


def test_citation_score_must_be_in_range() -> None:
    with pytest.raises(PydanticValidationError):
        Citation(doc_id="d", version=1, page=1, char_start=0, char_end=1, score=1.5)


def test_qa_request_requires_question() -> None:
    with pytest.raises(PydanticValidationError):
        QARequest(question="")


def test_qa_request_k_bounded() -> None:
    with pytest.raises(PydanticValidationError):
        QARequest(question="x", k=0)
    with pytest.raises(PydanticValidationError):
        QARequest(question="x", k=999)


def test_clause_type_enum_values() -> None:
    assert ClauseType("ip_assignment") is ClauseType.ip_assignment
