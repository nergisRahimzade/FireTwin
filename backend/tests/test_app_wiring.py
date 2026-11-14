"""Which routers main.py mounts in each mode (MOCK_MODE=0 real, MOCK_MODE=1 mocks)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ScenarioIn
from app.services import store
from ml.pipeline import model


@pytest.fixture
def real_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    # No key: rag.explain uses its offline template, so no network call happens.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "1")
    with TestClient(create_app()) as client:
        yield client


def _first_material() -> str:
    return sorted(model.load_table()["material"].dropna())[0]


def test_real_mode_serves_meta_from_the_table(real_client: TestClient) -> None:
    names = {m["name"] for m in real_client.get("/meta").json()["materials"]}
    assert names == set(model.load_table()["material"].dropna())


def test_real_mode_simulate_runs_the_predictor(real_client: TestClient) -> None:
    body = {"material": _first_material(), "o2_pct": 21, "flow_speed_cm_s": 10}
    response = real_client.post("/simulate", json=body)
    assert response.status_code == 200
    # Real ids come from the store (32 hex characters), not the mock's fixed id.
    assert response.json()["scenario_id"] != "synthetic-scenario-001"


def test_real_mode_apply_reuses_the_scenario(real_client: TestClient) -> None:
    body = {"material": _first_material(), "o2_pct": 21, "flow_speed_cm_s": 10}
    scenario_id = real_client.post("/simulate", json=body).json()["scenario_id"]
    response = real_client.post("/apply", json={"scenario_id": scenario_id, "action": "fans_off"})
    assert response.status_code == 200
    assert response.json()["scenario_id"] == scenario_id


def test_real_mode_lists_only_built_routes(real_client: TestClient) -> None:
    paths = set(real_client.get("/openapi.json").json()["paths"])
    assert paths == {
        "/health",
        "/simulate",
        "/apply",
        "/meta",
        "/detect",
        "/suppress",
        "/results/{scenario_id}",
        "/export/{scenario_id}.pdf",
    }


def test_mock_mode_meta_is_the_fixture(mock_client: TestClient) -> None:
    materials = mock_client.get("/meta").json()["materials"]
    assert [m["name"] for m in materials] == ["Synthetic cotton"]


def test_real_mode_results_returns_simulate_and_apply_history(real_client: TestClient) -> None:
    body = {"material": _first_material(), "o2_pct": 21, "flow_speed_cm_s": 10}
    simulated = real_client.post("/simulate", json=body)
    assert simulated.status_code == 200
    scenario_id = simulated.json()["scenario_id"]
    applied = real_client.post("/apply", json={"scenario_id": scenario_id, "action": "fans_off"})
    assert applied.status_code == 200
    response = real_client.get(f"/results/{scenario_id}")
    assert response.status_code == 200
    assert response.json() == {
        "scenario_id": scenario_id,
        "rows": json.loads(json.dumps(store.history(scenario_id))),
    }
    assert [row["step"] for row in response.json()["rows"]] == ["simulate", "apply"]


def test_mock_results_ignore_real_scenario_history(mock_client: TestClient) -> None:
    scenario_id = store.create(
        ScenarioIn(material="synthetic wiring fixture", o2_pct=21, flow_speed_cm_s=10)
    )
    store.append(scenario_id, "simulate", sources=["synthetic-wiring-test"])
    response = mock_client.get(f"/results/{scenario_id}")
    assert response.status_code == 200
    assert response.json()["scenario_id"] == "synthetic-scenario-001"
    assert len(response.json()["rows"]) == 3


def test_real_mode_exports_the_simulated_scenario(real_client: TestClient) -> None:
    body = {"material": _first_material(), "o2_pct": 21, "flow_speed_cm_s": 10}
    scenario_id = real_client.post("/simulate", json=body).json()["scenario_id"]
    history = store.history(scenario_id)
    response = real_client.get(f"/export/{scenario_id}.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert scenario_id.encode() in response.content
    assert store.history(scenario_id) == history
