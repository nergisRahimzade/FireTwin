"""POST /preview: the verdict for some inputs, with no scenario, history row or explanation."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import cache, rag, store


def _client(monkeypatch: pytest.MonkeyPatch, mode: str) -> TestClient:
    monkeypatch.setenv("MOCK_MODE", mode)
    return TestClient(create_app())


@pytest.fixture
def real(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return _client(monkeypatch, "0")


def _inputs(client: TestClient, o2: float = 21) -> dict:
    material = client.get("/meta").json()["materials"][0]["name"]
    return {"material": material, "o2_pct": o2, "flow_speed_cm_s": 10}


@pytest.mark.parametrize("o2", [12, 21, 30])
def test_preview_matches_the_simulate_verdict(real: TestClient, o2: float) -> None:
    # Same model and threshold, so a live preview never disagrees with the next Ignite.
    body = _inputs(real, o2)
    preview = real.post("/preview", json=body).json()
    simulated = real.post("/simulate", json=body).json()
    for key in ("state", "burn_probability", "trust", "extrapolated"):
        assert preview[key] == simulated[key], key
    assert preview["is_synthetic"] is False
    assert preview["inputs"] == simulated["inputs"]


def test_preview_creates_no_scenario_or_history(real: TestClient, monkeypatch) -> None:
    # Live views call this many times; none of it may show up in /results or the store.
    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not write to the scenario store")

    monkeypatch.setattr(store, "create", forbidden)
    monkeypatch.setattr(store, "append", forbidden)
    assert real.post("/preview", json=_inputs(real)).status_code == 200


def test_preview_writes_no_explanation(real: TestClient, monkeypatch) -> None:
    # The explanation is the slow part (an LLM call when a key is set); preview skips it.
    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not build an explanation")

    monkeypatch.setattr(rag, "explain", forbidden)
    monkeypatch.setattr(cache, "predict_and_explain", forbidden)
    assert real.post("/preview", json=_inputs(real)).status_code == 200


def test_non_finite_input_is_rejected_like_simulate(real: TestClient) -> None:
    raw = '{"material": "x", "o2_pct": NaN, "flow_speed_cm_s": 10}'
    response = real.post("/preview", content=raw, headers={"content-type": "application/json"})
    assert response.status_code == 422


def test_mock_preview_is_labelled_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "1")
    body = client.post("/preview", json=_inputs(client)).json()
    assert body["is_synthetic"] is True
