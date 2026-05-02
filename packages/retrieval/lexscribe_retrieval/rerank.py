"""Cross-encoder reranker interface, plus a deterministic heuristic fallback.

The heuristic is the default for tests and CI — it scores chunks by
question-token coverage with a length penalty. It is not as good as a real
cross-encoder, but it is free, deterministic, and produces *some* signal so the
rest of the pipeline can be exercised end-to-end without weights on disk.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

_TOK = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]: ...


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOK.finditer(text)}


@dataclass(frozen=True)
class HeuristicReranker:
    """Token-coverage with mild length penalty. Deterministic."""

    name: str = "heuristic-v1"

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]:
        q = _tokens(query)
        if not q:
            return [0.0] * len(candidates)
        out: list[float] = []
        for c in candidates:
            ct = _tokens(c)
            if not ct:
                out.append(0.0)
                continue
            overlap = len(q & ct)
            coverage = overlap / len(q)
            length_penalty = min(1.0, 600.0 / max(len(c), 1))
            out.append(coverage * (0.7 + 0.3 * length_penalty))
        return out
