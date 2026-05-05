"""Run a YAML eval suite end-to-end.

Suites live in two places:

* ``packages/eval/lexscribe_eval/suites/`` — synthetic suites shipped with
  the package (e.g. ``mna_v1``).
* ``eval/golden/`` (repo root) — hand-written golden suites against real
  corpora (e.g. ``mna_real_v1`` over the EDGAR seed). These are kept out of
  the package so the repo can ship them without bundling them into the
  installable wheel.

The ``corpus`` key in a suite YAML selects the index. Default is the
in-memory three-page demo corpus; ``corpus: edgar`` swaps in the EDGAR
seed via ``scripts.seed_edgar.build_corpus``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import yaml
from lexscribe_api.qa_service import answer_question, default_corpus
from lexscribe_shared.models import QARequest
from lexscribe_shared.providers import FakeLLMProvider, LLMProvider

from lexscribe_eval.metrics import EvalMetrics, score_run

_PACKAGE_SUITES = Path(__file__).parent / "suites"
_GOLDEN_ROOT = Path(__file__).resolve().parents[3] / "eval" / "golden"


def _suite_path(name: str) -> Path:
    """Return the YAML path for ``name`` from the first location that has it."""

    for root in (_PACKAGE_SUITES, _GOLDEN_ROOT):
        p = root / f"{name}.yaml"
        if p.exists():
            return p
    raise FileNotFoundError(f"unknown suite: {name}")


def load_suite(name: str) -> dict[str, Any]:
    return yaml.safe_load(_suite_path(name).read_text())


def _build_searcher(corpus: str | None):
    """Pick a corpus by name. Lazy imports so the synthetic path stays cheap."""

    if not corpus or corpus == "demo":
        return default_corpus()
    if corpus == "edgar":
        # ``scripts/`` is not a Python package; add it to sys.path on demand.
        scripts_dir = Path(__file__).resolve().parents[3] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from seed_edgar import build_corpus  # type: ignore[import-not-found]

        searcher, _docs = build_corpus()
        return searcher
    raise ValueError(f"unknown corpus: {corpus!r}")


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
    searcher = _build_searcher(suite.get("corpus"))

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
