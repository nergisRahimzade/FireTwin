"""BE-11: cached computations must not cache scenario identities, inputs or history writes."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import SimulateOut, TestRef
from app.services import cache, predictor, rag, store

BODY = {"material": "Synthetic cache API fixture", "o2_pct": 21, "flow_speed_cm_s": 10}
SOURCE = TestRef(
    test_id="synthetic-cache-api-001",
    investigation="Synthetic cache API fixture",
    fuel_type="solid",
    o2_pct=21,
    pressure_kpa=101.3,
    flow_cm_s=10,
    outcome="burned",
    source_url="https://example.com/synthetic-cache-api",
    is_synthetic=True,
)


@pytest.fixture
def service_calls(monkeypatch):
    calls = {"predict": [], "explain": []}

    def predict(inputs):
        calls["predict"].append(inputs.model_copy(deep=True))
        return (0.8 if inputs.flow_speed_cm_s else 0.2), None, "weak", True, [SOURCE]

    def explain(result):
        calls["explain"].append(result)
        return "Synthetic cache API explanation."

    monkeypatch.setattr(predictor, "predict", predict)
    monkeypatch.setattr(rag, "explain", explain)
    return calls


@pytest.fixture
def client(monkeypatch, service_calls):
    monkeypatch.setenv("MOCK_MODE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    cache.clear()
    store.clear()
    with TestClient(create_app()) as client:
        yield client
    cache.clear()
    store.clear()


def test_identical_simulations_compute_once_but_create_distinct_scenarios(client, service_calls):
    first = client.post("/simulate", json=BODY)
    second = client.post("/simulate", json=BODY)
    assert first.status_code == second.status_code == 200
    a, b = SimulateOut.model_validate(first.json()), SimulateOut.model_validate(second.json())
    assert a.scenario_id != b.scenario_id
    assert a.model_dump(exclude={"scenario_id"}) == b.model_dump(exclude={"scenario_id"})
    assert len(service_calls["predict"]) == len(service_calls["explain"]) == 1
    for sid in [a.scenario_id, b.scenario_id]:
        history = store.history(sid)
        assert len(history) == 1
        assert history[0]["step"] == "simulate"
        assert history[0]["probability"] == a.burn_probability
        assert history[0]["sources"] == [SOURCE.test_id]
    assert a.nearest_tests[0].is_synthetic is True


def test_repeated_apply_reuses_computation_but_records_each_action(client, service_calls):
    sid = client.post("/simulate", json=BODY).json()["scenario_id"]
    for _ in range(2):
        response = client.post("/apply", json={"scenario_id": sid, "action": "fans_off"})
        assert response.status_code == 200
        assert response.json()["state"] == "extinguished"
        assert response.json()["inputs"]["flow_speed_cm_s"] == 0
    assert len(service_calls["predict"]) == len(service_calls["explain"]) == 2
    history = client.get(f"/results/{sid}").json()["rows"]
    assert [r["step"] for r in history] == ["simulate", "apply", "apply"]
    assert [r["action"] for r in history] == [None, "fans_off", "fans_off"]
    assert [r["inputs"]["flow_speed_cm_s"] for r in history] == [10, 0, 0]
    assert [r["probability"] for r in history] == [0.8, 0.2, 0.2]
    assert store.get_inputs(sid).flow_speed_cm_s == 0


def test_noop_action_still_appends_history_on_a_cache_hit(client, service_calls):
    sid = client.post("/simulate", json=BODY).json()["scenario_id"]
    response = client.post("/apply", json={"scenario_id": sid, "action": "cut_power"})
    assert response.status_code == 200
    assert len(service_calls["predict"]) == len(service_calls["explain"]) == 1
    rows = store.history(sid)
    assert [r["step"] for r in rows] == ["simulate", "apply"]
    assert rows[-1]["action"] == "cut_power"


def test_new_scenario_can_reuse_a_previous_applied_result(client, service_calls):
    sid = client.post("/simulate", json=BODY).json()["scenario_id"]
    applied = client.post("/apply", json={"scenario_id": sid, "action": "fans_off"}).json()
    new = client.post("/simulate", json={**BODY, "flow_speed_cm_s": 0}).json()
    assert new["scenario_id"] != sid
    assert new["burn_probability"] == applied["burn_probability"] == 0.2
    assert len(service_calls["predict"]) == len(service_calls["explain"]) == 2
    assert [r["step"] for r in store.history(new["scenario_id"])] == ["simulate"]


def test_warm_cache_does_not_make_unknown_scenario_valid(client, service_calls):
    assert client.post("/simulate", json=BODY).status_code == 200
    response = client.post("/apply", json={"scenario_id": "unknown", "action": "cut_power"})
    assert response.status_code == 404
    assert len(service_calls["predict"]) == len(service_calls["explain"]) == 1


def test_mock_mode_never_calls_the_cache(monkeypatch):
    def fail(*args):
        pytest.fail("Mock endpoints must stay independent of the real computation cache")

    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setattr(cache, "predict_and_explain", fail)
    with TestClient(create_app()) as client:
        assert client.post("/simulate", json=BODY).status_code == 200
        response = client.post("/apply", json={"scenario_id": "unknown", "action": "fans_off"})
        assert response.status_code == 200
