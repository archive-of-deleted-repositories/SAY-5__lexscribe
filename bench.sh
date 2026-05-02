#!/usr/bin/env bash
# bench.sh — measurable end-to-end micro-benchmark.
#
# Runs N synthetic ingest+QA round-trips against the in-process pipeline using
# the FakeProvider. Prints wall-clock latency percentiles and cost per turn.
# Outputs JSON suitable for plotting.

set -euo pipefail

N=${N:-25}
PY=${PY:-python3}
ROOT=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="${ROOT}/packages/shared:${ROOT}/packages/retrieval:${ROOT}/packages/eval:${ROOT}/packages/clients/python:${ROOT}/services/api:${ROOT}/services/ingest-worker:${PYTHONPATH:-}"

"${PY}" - <<PYEOF
import json, statistics, time
from lexscribe_api.qa_service import answer_question, default_corpus
from lexscribe_shared.models import QARequest

QUESTIONS = [
    "What constitutes a Change of Control?",
    "Who owns intellectual property created during the engagement?",
    "What is the governing law of the agreement?",
    "Are there exclusivity restrictions on the contractor?",
    "What are the termination conditions?",
]

searcher = default_corpus()
lats = []
costs = []
n = ${N}
for i in range(n):
    q = QUESTIONS[i % len(QUESTIONS)]
    started = time.perf_counter()
    resp = answer_question(QARequest(question=q, k=8), searcher)
    lats.append(time.perf_counter() - started)
    costs.append(resp.usage.cost_usd)

lats_sorted = sorted(lats)
def pct(p):
    if not lats_sorted: return 0.0
    k = max(0, int(len(lats_sorted) * p / 100) - 1)
    return lats_sorted[k]

result = {
    "n": n,
    "p50_seconds": pct(50),
    "p95_seconds": pct(95),
    "p99_seconds": pct(99),
    "mean_seconds": statistics.fmean(lats),
    "mean_cost_usd": statistics.fmean(costs) if costs else 0.0,
    "provider": "fake",
}
print(json.dumps(result, indent=2))
PYEOF
