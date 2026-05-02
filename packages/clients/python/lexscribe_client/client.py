"""Thin httpx client. Why hand-written instead of generated?

* The schema is small enough that generation imports a 30MB toolchain for no win.
* We get to keep the client free of dataclass codegen boilerplate and reuse
  ``lexscribe_shared`` Pydantic models verbatim.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
from lexscribe_shared.errors import ErrorEnvelope, LexscribeError, RetryableError
from lexscribe_shared.models import QARequest, QAResponse


class LexscribeClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0, transport: Any = None) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LexscribeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- endpoints ---

    def healthz(self) -> dict[str, Any]:
        r = self._client.get("/healthz")
        return self._unwrap(r)

    def ask(self, question: str, *, k: int = 8, doc_ids: list[str] | None = None) -> QAResponse:
        req = QARequest(question=question, k=k, doc_ids=doc_ids)
        r = self._client.post("/qa", json=req.model_dump(mode="json"))
        return QAResponse.model_validate(self._unwrap(r))

    # --- helpers ---

    @staticmethod
    def _unwrap(r: httpx.Response) -> dict[str, Any]:
        if r.is_success:
            return r.json()
        try:
            env = ErrorEnvelope.model_validate(r.json())
        except Exception as exc:
            raise LexscribeError(f"HTTP {r.status_code}: {r.text[:200]}") from exc
        if env.retryable:
            raise RetryableError(env.message, details=env.details)
        raise LexscribeError(env.message, details=env.details)


@contextmanager
def client(base_url: str, **kwargs: Any) -> Iterator[LexscribeClient]:
    c = LexscribeClient(base_url, **kwargs)
    try:
        yield c
    finally:
        c.close()
