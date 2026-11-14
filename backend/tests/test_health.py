"""Tests for the app skeleton (BE-05): /health and CORS for the Vite dev server."""

from fastapi.testclient import TestClient

from app.main import create_app

VITE_ORIGIN = "http://localhost:5173"


def _client() -> TestClient:
    # A fresh app per test, so settings changed with monkeypatch are picked up.
    return TestClient(create_app())


def _preflight(client: TestClient, origin: str):
    # The OPTIONS request a browser sends before a cross-origin call, asking "may I?".
    return client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_health_returns_ok() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_vite_dev_server() -> None:
    response = _preflight(_client(), VITE_ORIGIN)
    assert response.headers.get("access-control-allow-origin") == VITE_ORIGIN


def test_cors_blocks_unknown_origin() -> None:
    response = _preflight(_client(), "http://evil.example.com")
    # No allow-origin header = the browser refuses to let that page read the response.
    assert "access-control-allow-origin" not in response.headers


def test_openapi_lists_health() -> None:
    # The frontend generates its types from /openapi.json (FE-01), so it must be served.
    paths = _client().get("/openapi.json").json()["paths"]
    assert "/health" in paths
