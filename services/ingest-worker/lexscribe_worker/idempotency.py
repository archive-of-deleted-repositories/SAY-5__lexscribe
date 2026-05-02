"""Per-stage idempotency keys.

Workers store ``(doc_id, version, stage)`` in Redis as soon as a stage
finishes. Re-running the task is a no-op: the worker reads the key first and
skips the body. This protects against duplicate work after a worker crash mid-
ack and removes the need for Celery dedup plugins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _Cache(Protocol):
    def get(self, key: str) -> bytes | str | None: ...
    def set(self, key: str, value: str, ex: int | None = None) -> None: ...


@dataclass
class IdempotencyStore:
    cache: _Cache
    ttl_seconds: int = 86_400 * 7

    @staticmethod
    def key(doc_id: str, version: int, stage: str, *, chunk_idx: int | None = None) -> str:
        if chunk_idx is None:
            return f"lex:idem:{doc_id}:{version}:{stage}"
        return f"lex:idem:{doc_id}:{version}:{stage}:{chunk_idx}"

    def already_done(self, key: str) -> bool:
        return self.cache.get(key) is not None

    def mark_done(self, key: str, *, value: str = "ok") -> None:
        self.cache.set(key, value, ex=self.ttl_seconds)


class InMemoryCache:
    """Thread-unsafe; for tests only."""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._d.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        del ex
        self._d[key] = value
