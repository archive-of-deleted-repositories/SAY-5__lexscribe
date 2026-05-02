"""LLM and embedding provider Protocols, plus deterministic fakes for tests.

The whole codebase routes generation and embedding through these Protocols so a
test run never reaches Anthropic/OpenAI. ``FakeProvider`` is fully deterministic:
identical input → identical output, byte-for-byte.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

from lexscribe_shared.models import Citation


@dataclass(frozen=True)
class GenerationRequest:
    system: str
    user: str
    chunks: tuple[str, ...]
    model: str
    max_tokens: int = 800


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    citation_indices: tuple[int, ...]
    tokens_in: int
    tokens_out: int
    model: str


class LLMProvider(Protocol):
    """Anything that turns a question + retrieved chunks into a structured answer."""

    name: str

    def generate(self, req: GenerationRequest) -> GenerationResult: ...


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


# ---------- Deterministic fakes ---------- #


def _seeded_vector(text: str, dim: int) -> list[float]:
    """Hash-seeded unit-ish vector. Deterministic and free."""

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    while len(out) < dim:
        for byte in digest:
            out.append((byte - 128) / 128.0)
            if len(out) == dim:
                break
        digest = hashlib.sha256(digest).digest()
    # Cheap normalisation
    norm = sum(x * x for x in out) ** 0.5 or 1.0
    return [x / norm for x in out]


@dataclass
class FakeEmbeddingProvider:
    """Hash-based deterministic embeddings."""

    dim: int = 1536
    name: str = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_seeded_vector(t, self.dim) for t in texts]


@dataclass
class FakeLLMProvider:
    """Returns the first chunk as the answer and cites it. Stable across runs."""

    name: str = "fake-llm"
    model: str = "fake-1"
    forced_citation_count: int = 1
    log: list[GenerationRequest] = field(default_factory=list)

    def generate(self, req: GenerationRequest) -> GenerationResult:
        self.log.append(req)
        if not req.chunks:
            return GenerationResult(
                answer="No relevant context was found.",
                citation_indices=(),
                tokens_in=len(req.user.split()),
                tokens_out=8,
                model=self.model,
            )
        first = req.chunks[0]
        snippet = first[:240].rsplit(" ", 1)[0]
        n_cites = min(self.forced_citation_count, len(req.chunks))
        return GenerationResult(
            answer=f"{snippet}",
            citation_indices=tuple(range(n_cites)),
            tokens_in=sum(len(c.split()) for c in req.chunks) + len(req.user.split()),
            tokens_out=len(snippet.split()),
            model=self.model,
        )


def attach_citations(chunk_meta: list[Citation], indices: tuple[int, ...]) -> list[Citation]:
    """Filter the candidate citation list down to those the LLM chose."""

    return [chunk_meta[i] for i in indices if 0 <= i < len(chunk_meta)]
