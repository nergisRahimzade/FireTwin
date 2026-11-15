"""The server announces the effective routing mode without printing settings or keys."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.mark.parametrize("mode", [None, "0", "1"])
def test_startup_reports_captured_mode_without_keys(monkeypatch, capfd, mode) -> None:
    monkeypatch.delenv("MOCK_MODE", raising=False)
    if mode is not None:
        monkeypatch.setenv("MOCK_MODE", mode)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-secret")
    app = create_app()
    # Later environment changes cannot mislabel an app that has already chosen its routers.
    monkeypatch.setenv("MOCK_MODE", "1" if mode == "0" else "0")
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    captured = capfd.readouterr()
    output = captured.out + captured.err
    expected = "real mode (MOCK_MODE=0)" if mode == "0" else "synthetic mock mode (MOCK_MODE=1)"
    assert f"FireTwin API: {expected}" in output
    assert "synthetic-openai-secret" not in output
    assert "synthetic-gemini-secret" not in output
