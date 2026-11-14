"""BE-08: read saved history through the real app, without network, ML calls or API keys."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ResultsOut, ScenarioIn
from app.services import store

ROW_KEYS = ["step", "inputs", "state", "probability", "trust", "detection_s", "action", "sources"]
SYNTHETIC_SOURCES = ["synthetic-results-test-001", "synthetic-results-test-002"]


def _inputs(flow: float = 10) -> ScenarioIn:
    return ScenarioIn(material="synthetic cotton", o2_pct=21, flow_speed_cm_s=flow)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    store.clear()
    with TestClient(create_app()) as client:
        yield client
    store.clear()


def test_results_returns_empty_history_for_existing_scenario(client: TestClient) -> None:
    scenario_id = store.create(_inputs())
    response = client.get(f"/results/{scenario_id}")
    assert response.status_code == 200
    assert response.json() == {"scenario_id": scenario_id, "rows": []}


def test_unknown_scenario_returns_404(client: TestClient) -> None:
    response = client.get("/results/unknown-scenario")
    assert response.status_code == 404
    assert "unknown-scenario" in response.json()["detail"]


def test_results_preserves_recorded_steps_in_order(client: TestClient) -> None:
    scenario_id = store.create(_inputs())
    store.append(
        scenario_id,
        "simulate",
        state="burning",
        probability=0.8,
        trust="weak",
        sources=SYNTHETIC_SOURCES,
    )
    store.append(scenario_id, "detect", detection_s=12.5, sources=SYNTHETIC_SOURCES)
    store.append(
        scenario_id,
        "apply",
        inputs=_inputs(flow=0),
        state="extinguished",
        probability=0.1,
        trust="weak",
        action="fans_off",
        sources=SYNTHETIC_SOURCES,
    )
    response = client.get(f"/results/{scenario_id}")
    assert response.status_code == 200
    result = ResultsOut.model_validate(response.json())
    assert result.scenario_id == scenario_id
    assert [row["step"] for row in result.rows] == ["simulate", "detect", "apply"]
    assert [list(row) for row in result.rows] == [ROW_KEYS] * 3


def test_results_preserves_historical_inputs_as_json_arrays(client: TestClient) -> None:
    scenario_id = store.create(_inputs(flow=10))
    store.append(scenario_id, "simulate", inputs=_inputs(flow=10))
    store.append(scenario_id, "apply", inputs=_inputs(flow=0), action="fans_off")
    store.set_inputs(scenario_id, _inputs(flow=20))
    rows = client.get(f"/results/{scenario_id}").json()["rows"]
    assert rows[0]["inputs"] == _inputs(flow=10).model_dump(mode="json")
    assert rows[1]["inputs"] == _inputs(flow=0).model_dump(mode="json")
    assert rows[0]["inputs"]["flow_dir"] == [1, 0, 0]


def test_results_preserves_null_values_from_detection(client: TestClient) -> None:
    scenario_id = store.create(_inputs())
    store.append(scenario_id, "detect", detection_s=None)
    row = client.get(f"/results/{scenario_id}").json()["rows"][0]
    assert row["state"] is None
    assert row["probability"] is None
    assert row["trust"] is None
    assert row["detection_s"] is None
    assert row["action"] is None
    assert row["sources"] == []


def test_results_preserves_probabilities_and_source_ids(client: TestClient) -> None:
    scenario_id = store.create(_inputs())
    store.append(
        scenario_id,
        "simulate",
        state="burning",
        probability=0.8,
        trust="weak",
        sources=SYNTHETIC_SOURCES,
    )
    row = client.get(f"/results/{scenario_id}").json()["rows"][0]
    assert row["state"] == "burning"
    assert row["probability"] == 0.8
    assert row["trust"] == "weak"
    assert row["sources"] == SYNTHETIC_SOURCES


def test_results_reads_do_not_change_inputs_or_history(client: TestClient) -> None:
    scenario_id = store.create(_inputs())
    store.append(scenario_id, "simulate", state="burning", sources=SYNTHETIC_SOURCES)
    previous_inputs = store.get_inputs(scenario_id).model_copy(deep=True)
    previous_history = store.history(scenario_id)
    first = client.get(f"/results/{scenario_id}")
    second = client.get(f"/results/{scenario_id}")
    assert first.json() == second.json()
    assert store.get_inputs(scenario_id) == previous_inputs
    assert store.history(scenario_id) == previous_history


def test_results_only_returns_the_requested_scenario(client: TestClient) -> None:
    first, second = store.create(_inputs()), store.create(_inputs())
    store.append(first, "simulate", sources=["synthetic-first"])
    store.append(second, "simulate", sources=["synthetic-second"])
    response = client.get(f"/results/{first}").json()
    assert response["scenario_id"] == first
    assert response["rows"][0]["sources"] == ["synthetic-first"]


def test_results_reflects_steps_appended_after_an_earlier_read(client: TestClient) -> None:
    scenario_id = store.create(_inputs())
    assert client.get(f"/results/{scenario_id}").json()["rows"] == []
    store.append(scenario_id, "detect", detection_s=12.5)
    rows = client.get(f"/results/{scenario_id}").json()["rows"]
    assert len(rows) == 1
    assert rows[0]["detection_s"] == 12.5


def test_results_is_404_after_store_is_cleared(client: TestClient) -> None:
    scenario_id = store.create(_inputs())
    store.clear()
    assert client.get(f"/results/{scenario_id}").status_code == 404


def test_results_is_documented_in_real_app_openapi(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/results/{scenario_id}"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/ResultsOut"}
    assert "404" in operation["responses"]
