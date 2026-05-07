"""Wire-level domain models. These are the contract — DB models live elsewhere."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DocumentStatus(str, Enum):
    pending = "pending"
    parsing = "parsing"
    embedding = "embedding"
    classifying = "classifying"
    active = "active"
    failed = "failed"


class ClauseType(str, Enum):
    """Bounded set of clause categories a span classifier may emit."""

    change_of_control = "change_of_control"
    ip_assignment = "ip_assignment"
    exclusivity = "exclusivity"
    termination = "termination"
    indemnity = "indemnity"
    governing_law = "governing_law"
    other = "other"


class Citation(BaseModel):
    """Span-level pointer back to the source document.

    ``chunk_hash`` and ``doc_canonical_hash`` are sha256 hex digests of the
    canonical text form (NFKC + lowercase + whitespace-collapse) of the chunk
    and the whole document respectively. They are populated at ingest by the
    worker and let downstream readers verify a citation has not silently
    drifted because the underlying doc-version was edited after the answer was
    served. See ``lexscribe verify-citation``.

    The fields default to ``None`` to keep the model backward-compatible with
    suites + corpora that pre-date the v3 hash schema.
    """

    model_config = ConfigDict(frozen=True)

    doc_id: str
    version: int = Field(ge=1)
    page: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)
    chunk_hash: str | None = None
    doc_canonical_hash: str | None = None


class Usage(BaseModel):
    tokens_in: int = Field(ge=0, default=0)
    tokens_out: int = Field(ge=0, default=0)
    cost_usd: float = Field(ge=0.0, default=0.0)


class QARequest(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=4000)]
    doc_ids: list[str] | None = None
    k: int = Field(default=8, ge=1, le=32)


class QAResponse(BaseModel):
    answer: str
    citations: list[Citation]
    usage: Usage
    model_version: str


class DocumentSummary(BaseModel):
    id: str
    sha256: str
    status: DocumentStatus
    current_version: int
    page_count: int | None = None


class CursorPage(BaseModel):
    """Generic cursor-paginated envelope."""

    items: list[dict]  # type: ignore[type-arg]
    next_cursor: str | None = None
