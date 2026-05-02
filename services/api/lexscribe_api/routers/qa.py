"""POST /qa — the user-facing hybrid-RAG endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter
from lexscribe_shared.models import QARequest, QAResponse

from lexscribe_api.metrics import qa_latency
from lexscribe_api.qa_service import answer_question, default_corpus

router = APIRouter(tags=["qa"])


@router.post("/qa", response_model=QAResponse)
def post_qa(req: QARequest) -> QAResponse:
    started = time.perf_counter()
    try:
        return answer_question(req, default_corpus())
    finally:
        qa_latency.observe(time.perf_counter() - started)
