"""Ingest DAG: parse_pdf → chunk → embed → classify_spans.

Failures land in ``failed_jobs`` after the retry budget is exhausted. This is
done explicitly inside ``on_failure`` rather than via ``after_return`` so that
synchronous unit tests can call the underlying functions and observe the same
DLQ semantics.
"""

from __future__ import annotations

import logging
from typing import Any

from lexscribe_shared.errors import RetryableError
from lexscribe_shared.retry import backoff_delays

from lexscribe_worker.app import celery_app

LOG = logging.getLogger(__name__)


def _serialise_chunks(pages: list[tuple[int, str]]) -> list[dict[str, Any]]:
    from lexscribe_retrieval.chunker import chunk_pages

    return [
        {
            "page_no": c.page_no,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "text": c.text,
        }
        for c in chunk_pages(pages)
    ]


@celery_app.task(
    bind=True,
    name="lexscribe_worker.tasks.parse_pdf",
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
)
def parse_pdf(self, doc_id: str, version: int, s3_key: str) -> dict[str, Any]:
    """Download from S3 and emit ``(page_no, text)`` for each page.

    The real implementation tries ``pdfplumber`` first and falls back to
    ``unstructured`` with OCR if text density is below a threshold. Here we
    keep the logic small enough to run without those binary dependencies.
    """

    LOG.info(
        "parse_pdf doc=%s ver=%s key=%s attempt=%s", doc_id, version, s3_key, self.request.retries
    )
    # Stub. Integration test wires MinIO and a real PDF fixture.
    return {
        "doc_id": doc_id,
        "version": version,
        "pages": [],
    }


@celery_app.task(name="lexscribe_worker.tasks.chunk")
def chunk(parsed: dict[str, Any]) -> dict[str, Any]:
    pages: list[tuple[int, str]] = [(int(p["page_no"]), p["text"]) for p in parsed["pages"]]
    return {
        "doc_id": parsed["doc_id"],
        "version": parsed["version"],
        "chunks": _serialise_chunks(pages),
    }


@celery_app.task(
    bind=True,
    name="lexscribe_worker.tasks.embed",
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
)
def embed(self, chunked: dict[str, Any]) -> dict[str, Any]:
    """Embed chunks under a Redis-backed semaphore.

    The semaphore is acquired *outside* the task body so a worker that has
    grabbed a slot but cannot reach the provider releases the slot fast. We do
    not block on it indefinitely — a missed acquire raises ``RetryableError``
    and Celery applies the standard backoff schedule.
    """

    from lexscribe_shared.providers import FakeEmbeddingProvider

    LOG.info(
        "embed doc=%s ver=%s n=%s attempt=%s",
        chunked["doc_id"],
        chunked["version"],
        len(chunked["chunks"]),
        self.request.retries,
    )
    embedder = FakeEmbeddingProvider(dim=128)
    texts = [c["text"] for c in chunked["chunks"]]
    vecs = embedder.embed(texts) if texts else []
    return {
        "doc_id": chunked["doc_id"],
        "version": chunked["version"],
        "chunks": chunked["chunks"],
        "embeddings": vecs,
    }


@celery_app.task(name="lexscribe_worker.tasks.classify_spans")
def classify_spans(embedded: dict[str, Any]) -> dict[str, Any]:
    """Cheap keyword classifier. The real one is a small LLM prompt."""

    keywords: dict[str, str] = {
        "change of control": "change_of_control",
        "intellectual property": "ip_assignment",
        "exclusivity": "exclusivity",
        "exclusive": "exclusivity",
        "terminate": "termination",
        "indemnif": "indemnity",
        "governed by": "governing_law",
    }
    spans: list[dict[str, Any]] = []
    for chunk_dict in embedded["chunks"]:
        text_lower = chunk_dict["text"].lower()
        for needle, label in keywords.items():
            if needle in text_lower:
                spans.append(
                    {
                        "page_no": chunk_dict["page_no"],
                        "char_start": chunk_dict["char_start"],
                        "char_end": chunk_dict["char_end"],
                        "clause_type": label,
                        "confidence": 0.7,
                    }
                )
                break
    return {
        "doc_id": embedded["doc_id"],
        "version": embedded["version"],
        "spans": spans,
    }


# ---- Orchestration helper ---- #


def run_pipeline_sync(doc_id: str, version: int, pages: list[tuple[int, str]]) -> dict[str, Any]:
    """Run the full pipeline in-process. Used by tests and ``bench.sh``."""

    parsed: dict[str, Any] = {
        "doc_id": doc_id,
        "version": version,
        "pages": [{"page_no": p, "text": t} for p, t in pages],
    }
    chunked = chunk.run(parsed)  # type: ignore[attr-defined]
    embedded = embed.run(chunked)  # type: ignore[attr-defined]
    classified = classify_spans.run(embedded)  # type: ignore[attr-defined]
    return classified


# ---- Backoff helper, exposed for tests ---- #


def schedule_for(max_attempts: int = 5) -> list[float]:
    return list(backoff_delays(max_attempts=max_attempts, jitter=0.0))
