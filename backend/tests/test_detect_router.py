"""POST /detect through the real app (MOCK_MODE=0): response, history row and errors."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import DetectOut
from app.services import store
from ml.pipeline import config, model


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    # No key: rag.explain uses its offline template, so no network call happens.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app()) as client:
        yield client


def _simulate(client: TestClient, flow: float = 10) -> str:
    material = sorted(model.load_table()["material"].dropna())[0]
    body = {"material": material, "o2_pct": 21, "flow_speed_cm_s": flow}
    return client.post("/simulate", json=body).json()["scenario_id"]


def test_detect_returns_the_contract_shape(client: TestClient) -> None:
    response = client.post("/detect", json={"scenario_id": _simulate(client)})
    assert response.status_code == 200
    DetectOut.model_validate(response.json())


def test_detect_appends_a_detect_row(client: TestClient) -> None:
    scenario_id = _simulate(client)
    detected = client.post("/detect", json={"scenario_id": scenario_id}).json()
    simulate_row, detect_row = store.history(scenario_id)
    assert detect_row["step"] == "detect"
    assert detect_row["detection_s"] == detected["time_to_detect_s"]
    # No new verdict on a detect step.
    assert detect_row["state"] is detect_row["probability"] is None
    # Same sources as the verdict it belongs to, so the results table can badge them.
    assert detect_row["sources"] == simulate_row["sources"]


def test_fans_off_is_never_detected(client: TestClient) -> None:
    detected = client.post("/detect", json={"scenario_id": _simulate(client, flow=0)}).json()
    assert detected["detected"] is False
    assert detected["time_to_detect_s"] is None
    assert detected["note"] == config.NOTE_FANS_OFF


def test_detect_unknown_scenario_is_404(client: TestClient) -> None:
    response = client.post("/detect", json={"scenario_id": "never-created"})
    assert response.status_code == 404
    assert "never-created" in response.json()["detail"]


def test_detect_requires_a_scenario_id(client: TestClient) -> None:
    assert client.post("/detect", json={}).status_code == 422
