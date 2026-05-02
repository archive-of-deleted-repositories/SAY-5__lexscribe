from __future__ import annotations

import pytest
from lexscribe_shared.cursor import CursorCodec, decode_cursor, encode_cursor


def test_round_trip_basic_payload() -> None:
    payload = {"created_at": "2026-01-02T03:04:05Z", "id": "doc_abc"}
    cur = encode_cursor(payload)
    assert "/" not in cur and "+" not in cur and "=" not in cur
    assert decode_cursor(cur) == payload


def test_round_trip_through_codec() -> None:
    codec = CursorCodec(("created_at", "id"))
    cur = codec.encode(created_at="2026-01-02T03:04:05Z", id="doc_xyz")
    decoded = codec.decode(cur)
    assert decoded["id"] == "doc_xyz"


def test_codec_rejects_missing_field_on_encode() -> None:
    codec = CursorCodec(("created_at", "id"))
    with pytest.raises(ValueError):
        codec.encode(created_at="x")  # missing id


def test_codec_rejects_missing_field_on_decode() -> None:
    codec = CursorCodec(("created_at", "id"))
    bad = encode_cursor({"created_at": "x"})  # missing id
    with pytest.raises(ValueError):
        codec.decode(bad)


def test_decode_rejects_non_object() -> None:
    # Plain non-dict JSON encoded via the same scheme should fail to decode.
    import base64
    import json

    raw = json.dumps([1, 2, 3]).encode("utf-8")
    cur = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    with pytest.raises(ValueError):
        decode_cursor(cur)
    # encode_cursor itself accepts any dict (sanity)
    assert encode_cursor({"x": 1})
