"""BE-02: /simulate and /apply, plus the full service loop with no LLM key."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import simulate as simulate_router
from app.schemas import ScenarioIn
from app.services import detector, rag, store, suppressor

BASE = {"material": "cable insulation", "o2_pct": 21.0, "flow_speed_cm_s": 10.0}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store.clear()
    app = FastAPI()
    app.include_router(simulate_router.router)
    return TestClient(app)


def test_simulate_returns_a_verdict_with_three_sources(client) -> None:
    out = client.post("/simulate", json=BASE)
    assert out.status_code == 200
    body = out.json()
    assert body["state"] == "burning"
    assert body["burn_probability"] >= 0.5
    assert body["trust"] in {"strong", "medium", "weak"}
    assert body["extrapolated"] is False
    assert len(body["nearest_tests"]) == 3
    assert body["nearest_tests"][0]["test_id"] in body["explanation"]
    assert body["inputs"]["o2_pct"] == 21.0


def test_simulate_stores_a_history_row(client) -> None:
    sid = client.post("/simulate", json=BASE).json()["scenario_id"]
    rows = store.history(sid)
    assert [r["step"] for r in rows] == ["simulate"]
    assert rows[0]["state"] == "burning" and len(rows[0]["sources"]) == 3


def test_state_follows_the_half_probability_threshold(client) -> None:
    body = client.post("/simulate", json={**BASE, "o2_pct": 14.0, "flow_speed_cm_s": 0.0}).json()
    assert body["burn_probability"] < 0.5
    assert body["state"] == "extinguished"


def test_outside_range_inputs_are_flagged(client) -> None:
    body = client.post("/simulate", json={**BASE, "o2_pct": 34.0}).json()
    assert body["extrapolated"] is True
    assert body["trust"] == "weak"
    assert "no direct NASA data" in body["explanation"]


def test_apply_uses_the_actions_new_inputs_and_appends_a_row(client) -> None:
    sid = client.post("/simulate", json=BASE).json()["scenario_id"]
    out = client.post("/apply", json={"scenario_id": sid, "action": "fans_off_co2"})
    assert out.status_code == 200
    body = out.json()
    assert body["scenario_id"] == sid
    assert body["inputs"]["flow_speed_cm_s"] == 0.0
    assert body["inputs"]["o2_pct"] == 15.0
    assert body["state"] == "extinguished"
    rows = store.history(sid)
    assert [r["step"] for r in rows] == ["simulate", "apply"]
    assert rows[1]["action"] == "fans_off_co2"
    assert store.get_inputs(sid).flow_speed_cm_s == 0.0


def test_a_worse_action_leaves_the_fire_burning(client) -> None:
    sid = client.post("/simulate", json=BASE).json()["scenario_id"]
    body = client.post("/apply", json={"scenario_id": sid, "action": "water_mist"}).json()
    assert body["state"] == "burning"


def test_actions_stack_across_apply_calls(client) -> None:
    sid = client.post("/simulate", json=BASE).json()["scenario_id"]
    client.post("/apply", json={"scenario_id": sid, "action": "fans_off"})
    body = client.post("/apply", json={"scenario_id": sid, "action": "co2"}).json()
    assert (body["inputs"]["flow_speed_cm_s"], body["inputs"]["o2_pct"]) == (0.0, 15.0)


def test_apply_to_an_unknown_scenario_is_404(client) -> None:
    out = client.post("/apply", json={"scenario_id": "nope", "action": "fans_off"})
    assert out.status_code == 404
    assert "nope" in out.json()["detail"]


def test_apply_with_an_unknown_action_is_422(client) -> None:
    sid = client.post("/simulate", json=BASE).json()["scenario_id"]
    out = client.post("/apply", json={"scenario_id": sid, "action": "halon"})
    assert out.status_code == 422


def test_explainer_failure_does_not_break_simulate(client, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")

    def boom(system: str, user: str) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(rag, "_chat", boom)
    out = client.post("/simulate", json=BASE)
    assert out.status_code == 200 and out.json()["explanation"]


def test_full_loop_simulate_detect_suppress_apply_results(client) -> None:
    sid = client.post("/simulate", json=BASE).json()["scenario_id"]
    inputs = store.get_inputs(sid)
    assert isinstance(inputs, ScenarioIn)

    detection = detector.detect(inputs)
    store.append(sid, "detect", detection_s=detection.time_to_detect_s)
    assert detection.detected

    ranking = suppressor.suppress(sid, inputs)
    applied = client.post("/apply", json={"scenario_id": sid, "action": ranking.recommended})
    assert applied.json()["state"] == "extinguished"

    rows = store.history(sid)
    assert [r["step"] for r in rows] == ["simulate", "detect", "apply"]
    assert rows[1]["detection_s"] == 40.0
    assert rows[2]["action"] == ranking.recommended
