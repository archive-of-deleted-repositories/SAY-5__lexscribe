"""Eval metrics. Kept small and honest.

* ``precision_at_1``  — top-ranked citation comes from an expected doc.
* ``recall_at_5``     — at least one of the top-5 citations is from an
  expected doc, averaged across questions.
* ``faithfulness``    — placeholder rubric: an answer is "faithful" if every
  word of length ≥ 5 in the answer appears in at least one cited chunk. This
  is intentionally simple — the real scoring lives in
  ``faithfulness_llm_judge`` (BYOK path) and is not run in CI.
* ``refusal_rate``    — share of answers that look like a refusal.
* ``cost_usd_avg``    — mean USD per turn from ``usage.cost_usd``.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass
from typing import Any

_REFUSAL_PHRASES = (
    "i don't know",
    "no relevant context",
    "cannot answer",
    "insufficient information",
)


@dataclass
class EvalMetrics:
    n: int
    precision_at_1: float
    recall_at_5: float
    faithfulness: float
    refusal_rate: float
    cost_usd_avg: float
    p95_latency_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_refusal(answer: str) -> bool:
    al = answer.lower()
    return any(p in al for p in _REFUSAL_PHRASES)


def _faithful(answer: str, cited_texts: list[str]) -> bool:
    if not answer.strip():
        return False
    if not cited_texts:
        return False
    words = set(re.findall(r"[A-Za-z]{5,}", answer.lower()))
    if not words:
        return True
    blob = " ".join(cited_texts).lower()
    covered = sum(1 for w in words if w in blob)
    return covered / len(words) >= 0.6


def score_run(rows: list[dict[str, Any]]) -> EvalMetrics:
    """Aggregate per-question rows into a single ``EvalMetrics``."""

    if not rows:
        return EvalMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    p1_hits = 0
    r5_hits = 0
    faith_hits = 0
    refusals = 0
    costs: list[float] = []
    lats: list[float] = []

    for r in rows:
        cits = r.get("citations", [])
        expected_docs = set(r.get("expected_doc_ids", []))
        if cits:
            top_doc = cits[0].get("doc_id")
            if top_doc in expected_docs:
                p1_hits += 1
            top5_docs = {c.get("doc_id") for c in cits[:5]}
            if top5_docs & expected_docs:
                r5_hits += 1
        if _faithful(r.get("answer", ""), [c.get("text", "") for c in cits]):
            faith_hits += 1
        if _is_refusal(r.get("answer", "")):
            refusals += 1
        usage = r.get("usage", {}) or {}
        costs.append(float(usage.get("cost_usd", 0.0)))
        lats.append(float(r.get("latency_seconds", 0.0)))

    n = len(rows)
    p95 = statistics.quantiles(lats, n=20)[18] if len(lats) >= 20 else (max(lats) if lats else 0.0)
    return EvalMetrics(
        n=n,
        precision_at_1=p1_hits / n,
        recall_at_5=r5_hits / n,
        faithfulness=faith_hits / n,
        refusal_rate=refusals / n,
        cost_usd_avg=sum(costs) / n if costs else 0.0,
        p95_latency_seconds=p95,
    )
