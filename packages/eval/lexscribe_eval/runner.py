"""Run a YAML eval suite end-to-end."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml
from lexscribe_api.qa_service import answer_question, default_corpus
from lexscribe_shared.models import QARequest
from lexscribe_shared.providers import FakeLLMProvider, LLMProvider

from lexscribe_eval.metrics import EvalMetrics, score_run

_SUITES = Path(__file__).parent / "suites"


def load_suite(name: str) -> dict[str, Any]:
    p = _SUITES / f"{name}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"unknown suite: {name}")
    return yaml.safe_load(p.read_text())


def run_suite(
    name: str,
    *,
    provider: LLMProvider | None = None,
    limit: int | None = None,
    model: str | None = None,
) -> tuple[EvalMetrics, list[dict[str, Any]]]:
    suite = load_suite(name)
    questions = suite.get("questions", [])
    if limit is not None:
        questions = questions[:limit]

    llm = provider or FakeLLMProvider(model=model or "fake-1")
    searcher = default_corpus()

    rows: list[dict[str, Any]] = []
    for q in questions:
        started = time.perf_counter()
        resp = answer_question(QARequest(question=q["question"], k=8), searcher, llm=llm)
        elapsed = time.perf_counter() - started
        rows.append(
            {
                "question_id": q["id"],
                "question": q["question"],
                "expected_clause_types": q.get("expected_clause_types", []),
                "expected_doc_ids": q.get("expected_doc_ids", []),
                "answer": resp.answer,
                "citations": [c.model_dump() for c in resp.citations],
                "usage": resp.usage.model_dump(),
                "model_version": resp.model_version,
                "latency_seconds": elapsed,
            }
        )

    metrics = score_run(rows)
    return metrics, rows
