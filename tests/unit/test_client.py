from __future__ import annotations

import httpx
from lexscribe_client import LexscribeClient


def test_ask_round_trip_against_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/qa"
        return httpx.Response(
            200,
            json={
                "answer": "Delaware governs.",
                "citations": [
                    {
                        "doc_id": "doc_x",
                        "version": 1,
                        "page": 3,
                        "char_start": 0,
                        "char_end": 50,
                        "score": 0.9,
                    }
                ],
                "usage": {"tokens_in": 10, "tokens_out": 5, "cost_usd": 0.001},
                "model_version": "fake-1",
            },
        )

    transport = httpx.MockTransport(handler)
    with LexscribeClient("http://test", transport=transport) as c:
        resp = c.ask("What is the governing law?")
        assert resp.answer == "Delaware governs."
        assert resp.citations[0].page == 3


def test_client_raises_on_error_envelope() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"code": "validation_error", "message": "bad", "retryable": False},
        )

    transport = httpx.MockTransport(handler)
    import pytest
    from lexscribe_shared.errors import LexscribeError

    with (
        LexscribeClient("http://test", transport=transport) as c,
        pytest.raises(LexscribeError),
    ):
        c.ask("bad")
