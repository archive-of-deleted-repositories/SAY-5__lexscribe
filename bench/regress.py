"""Bench regression gate.

Compare a fresh bench run JSON against a committed baseline JSON. Exits 1 if
any tracked metric drifts more than ``--threshold`` (default 30%) from the
baseline.

Tracked metrics:

* ``docs_per_sec``         — ingest throughput (lower → regression)
* ``chunks_per_sec``       — ingest throughput (lower → regression)
* ``ingest_stage_ms.<s>.p95``      for s in (parse, chunk, embed, classify) (higher → regression)
* ``retrieval_stage_us_hdr.<s>.p95_us`` for s in (bm25, dense, fusion, rerank) (higher → regression)
* ``end_to_end_qa_ms.p95`` — e2e turn latency (higher → regression)
* ``cost_per_turn_usd.mean``       (higher → regression)

The drift is signed: throughput metrics regress when the new value drops, latency
and cost metrics regress when the new value rises. Both directions count toward
the threshold so a 30% improvement does not trigger the gate.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricSpec:
    path: tuple[str, ...]
    direction: str  # "higher_better" or "lower_better"

    def label(self) -> str:
        return ".".join(self.path)

    def lookup(self, payload: dict[str, Any]) -> float | None:
        cur: Any = payload
        for key in self.path:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        if not isinstance(cur, int | float):
            return None
        return float(cur)


METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(("docs_per_sec",), "higher_better"),
    MetricSpec(("chunks_per_sec",), "higher_better"),
    MetricSpec(("ingest_stage_ms", "parse", "p95"), "lower_better"),
    MetricSpec(("ingest_stage_ms", "chunk", "p95"), "lower_better"),
    MetricSpec(("ingest_stage_ms", "embed", "p95"), "lower_better"),
    MetricSpec(("ingest_stage_ms", "classify", "p95"), "lower_better"),
    MetricSpec(("retrieval_stage_us_hdr", "bm25", "p95_us"), "lower_better"),
    MetricSpec(("retrieval_stage_us_hdr", "dense", "p95_us"), "lower_better"),
    MetricSpec(("retrieval_stage_us_hdr", "fusion", "p95_us"), "lower_better"),
    MetricSpec(("retrieval_stage_us_hdr", "rerank", "p95_us"), "lower_better"),
    MetricSpec(("end_to_end_qa_ms", "p95"), "lower_better"),
    MetricSpec(("cost_per_turn_usd", "mean"), "lower_better"),
)


def _signed_drift(baseline: float, new: float, direction: str) -> float:
    """Return signed drift as a fraction of baseline.

    Positive drift = regression; negative drift = improvement.
    Zero baseline is treated as 1.0 to avoid division-by-zero spikes — the
    metric is then considered drifted only if the new value exceeds 1.0 absolute.
    """

    base = baseline if baseline != 0.0 else 1.0
    if direction == "higher_better":
        return (baseline - new) / base
    return (new - baseline) / base


def compare(baseline: dict[str, Any], new: dict[str, Any], threshold: float) -> list[str]:
    """Return a list of regression failure messages. Empty list = pass."""

    failures: list[str] = []
    for m in METRICS:
        b = m.lookup(baseline)
        n = m.lookup(new)
        if b is None or n is None:
            continue
        drift = _signed_drift(b, n, m.direction)
        if drift > threshold:
            failures.append(
                f"{m.label()} regressed by {drift * 100:.1f}% "
                f"(baseline={b:.6g}, new={n:.6g}, direction={m.direction})"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bench regression gate.")
    p.add_argument("--baseline", type=Path, required=True, help="committed baseline JSON")
    p.add_argument("--new", type=Path, required=True, help="fresh bench run JSON")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="max allowed signed drift (fraction of baseline; default 0.30 = 30%%)",
    )
    args = p.parse_args(argv)

    baseline = json.loads(args.baseline.read_text())
    new = json.loads(args.new.read_text())
    failures = compare(baseline, new, args.threshold)

    if failures:
        print(f"# bench-regress FAIL — {len(failures)} metric(s) drifted past {args.threshold:.0%}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"# bench-regress PASS — no metric drifted past {args.threshold:.0%}")
    print(f"# baseline: {args.baseline}")
    print(f"# new     : {args.new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
