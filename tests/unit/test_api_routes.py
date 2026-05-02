from __future__ import annotations

from fastapi.testclient import TestClient
from lexscribe_api.main import app


def test_livez() -> None:
    with TestClient(app) as c:
        r = c.get("/livez")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_healthz_includes_subsystems() -> None:
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert set(body["checks"]) >= {"postgres", "redis", "s3", "provider"}


def test_create_document_returns_presigned_response() -> None:
    with TestClient(app) as c:
        r = c.post(
            "/documents",
            json={
                "filename": "deal.pdf",
                "sha256": "a" * 64,
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["s3_key"].endswith("deal.pdf")
        assert body["expires_in"] > 0


def test_create_document_rejects_bad_sha() -> None:
    with TestClient(app) as c:
        r = c.post(
            "/documents",
            json={"filename": "x.pdf", "sha256": "short"},
        )
        assert r.status_code == 422


def test_qa_returns_envelope() -> None:
    with TestClient(app) as c:
        r = c.post("/qa", json={"question": "What is the governing law?"})
        assert r.status_code == 200
        body = r.json()
        assert "answer" in body
        assert "citations" in body
        assert "usage" in body
        assert "model_version" in body


def test_request_id_is_returned() -> None:
    with TestClient(app) as c:
        r = c.get("/livez", headers={"x-request-id": "test-1234"})
        assert r.headers["x-request-id"] == "test-1234"


def test_metrics_endpoint_is_mounted() -> None:
    with TestClient(app) as c:
        r = c.get("/metrics/")
        assert r.status_code == 200
        assert b"lexscribe_qa_latency_seconds" in r.content or r.content
