"""POST /suppress through the real app (MOCK_MODE=0): ranking, links to /apply, and errors."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import SuppressOut
from app.services import store
from ml.pipeline import model

ACTIONS = {"fans_off", "cut_power", "co2", "water_mist", "fans_off_co2"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app()) as client:
        yield client


def _simulate(client: TestClient) -> str:
    material = sorted(model.load_table()["material"].dropna())[0]
    body = {"material": material, "o2_pct": 21, "flow_speed_cm_s": 10}
    return client.post("/simulate", json=body).json()["scenario_id"]


def test_suppress_ranks_all_five_actions(client: TestClient) -> None:
    scenario_id = _simulate(client)
    result = SuppressOut.model_validate(
        client.post("/suppress", json={"scenario_id": scenario_id}).json()
    )
    assert result.scenario_id == scenario_id
    assert {action.action for action in result.actions} == ACTIONS
    # Order documented in docs/contract.md ("POST /suppress: order of actions"): data-backed
    # actions by score, then no-data actions by score with water_mist last.
    backed = [a for a in result.actions if a.data_support != "none"]
    unbacked = [a for a in result.actions if a.data_support == "none"]
    assert result.actions == backed + unbacked
    assert [a.score for a in backed] == sorted((a.score for a in backed), reverse=True)
    others = [a for a in unbacked if a.action != "water_mist"]
    assert [a.score for a in others] == sorted((a.score for a in others), reverse=True)
    assert unbacked[-1].action == "water_mist"
    assert result.recommended == (backed[0].action if backed else "cut_power")


def test_suppress_adds_no_history_row(client: TestClient) -> None:
    scenario_id = _simulate(client)
    client.post("/suppress", json={"scenario_id": scenario_id})
    assert [row["step"] for row in store.history(scenario_id)] == ["simulate"]


def test_applying_the_recommendation_uses_its_new_inputs(client: TestClient) -> None:
    # What the e2e loop checks: /apply lands on exactly the inputs /suppress promised.
    scenario_id = _simulate(client)
    ranked = client.post("/suppress", json={"scenario_id": scenario_id}).json()
    best = ranked["actions"][0]
    body = {"scenario_id": scenario_id, "action": best["action"]}
    applied = client.post("/apply", json=body).json()
    assert applied["inputs"] == best["new_inputs"]


def test_suppress_unknown_scenario_is_404(client: TestClient) -> None:
    assert client.post("/suppress", json={"scenario_id": "never-created"}).status_code == 404
