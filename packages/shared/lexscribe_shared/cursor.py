"""Opaque cursor codec for keyset pagination.

Cursors encode the last-seen sort key (typically ``(created_at, id)``). They are
base64url-encoded JSON so callers cannot meaningfully introspect them — but they
are not signed, so the server must still validate that the decoded keys are
shaped correctly before issuing a query.
"""

from __future__ import annotations

import base64
import json
from typing import Any


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> dict[str, Any]:
    padding = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + padding)
    out = json.loads(raw.decode("utf-8"))
    if not isinstance(out, dict):
        raise ValueError("cursor must decode to an object")
    return out


class CursorCodec:
    """Tiny helper that pairs ``encode``/``decode`` with a schema check."""

    def __init__(self, fields: tuple[str, ...]) -> None:
        self._fields = fields

    def encode(self, **kwargs: Any) -> str:
        missing = [f for f in self._fields if f not in kwargs]
        if missing:
            raise ValueError(f"cursor missing fields: {missing}")
        return encode_cursor({k: kwargs[k] for k in self._fields})

    def decode(self, cursor: str) -> dict[str, Any]:
        out = decode_cursor(cursor)
        missing = [f for f in self._fields if f not in out]
        if missing:
            raise ValueError(f"cursor missing fields: {missing}")
        return out
