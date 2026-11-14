"""End-to-end loop through the real routers and services, with no LLM key:
meta -> simulate -> detect -> suppress -> apply -> results -> chat -> export.

The main loop runs on the synthetic seed fixture (see the root conftest.py), where the outcome is
known. A second test runs the same calls on the committed NASA table and checks structure only.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import loop, meta, simulate
from app.services import store
from ml.pipeline import model


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store.clear()
    # The real routers, assembled here: main.py does not mount /detect, /suppress, /results,
    # /chat and /export yet. Once it does, this can become create_app() with MOCK_MODE=0.
    app = FastAPI()
    for module in (simulate, meta, loop):
        app.include_router(module.router)
    with TestClient(app) as test_client:
        yield test_client


def _run_loop(client: TestClient, scenario: dict) -> dict:
    """Call every endpoint in demo order and return each response body."""
    out = {}
    out["meta"] = client.get("/meta")
    out["simulate"] = client.post("/simulate", json=scenario)
    sid = out["simulate"].json()["scenario_id"]
    out["detect"] = client.post("/detect", json={"scenario_id": sid})
    out["suppress"] = client.post("/suppress", json={"scenario_id": sid})
    action = out["suppress"].json()["recommended"]
    out["apply"] = client.post("/apply", json={"scenario_id": sid, "action": action})
    out["results"] = client.get(f"/results/{sid}")
    out["chat"] = client.post("/chat", json={"message": "Why did that work?", "scenario_id": sid})
    out["export"] = client.get(f"/export/{sid}.pdf")
    failed = {name: r.status_code for name, r in out.items() if r.status_code != 200}
    assert not failed, f"endpoints that did not return 200: {failed}"
    return out


def test_full_loop_on_seed_data(client) -> None:
    scenario = {"material": "cable insulation", "o2_pct": 21.0, "flow_speed_cm_s": 10.0}
    out = _run_loop(client, scenario)

    assert "cable insulation" in {m["name"] for m in out["meta"].json()["materials"]}
    simulate = out["simulate"].json()
    assert simulate["state"] == "burning" and len(simulate["nearest_tests"]) == 3

    detect = out["detect"].json()
    assert detect["detected"] and detect["detector_id"] == "vent_fwd"
    assert detect["time_to_detect_s"] == 40.0

    suppress = out["suppress"].json()
    assert len(suppress["actions"]) == 5
    assert suppress["actions"][0]["action"] == suppress["recommended"]
    assert suppress["actions"][-1]["action"] == "water_mist"

    assert out["apply"].json()["state"] == "extinguished"

    rows = out["results"].json()["rows"]
    assert [r["step"] for r in rows] == ["simulate", "detect", "apply"]
    assert rows[1]["detection_s"] == 40.0
    assert rows[1]["sources"] == rows[0]["sources"]
    assert rows[2]["action"] == suppress["recommended"]

    assert out["chat"].json()["answer"]
    assert out["export"].headers["content-type"] == "application/pdf"
    assert out["export"].content.startswith(b"%PDF") and len(out["export"].content) > 1000


def test_fans_off_then_detect_reports_smoke_cannot_reach_vents(client) -> None:
    scenario = {"material": "cable insulation", "o2_pct": 21.0, "flow_speed_cm_s": 10.0}
    sid = client.post("/simulate", json=scenario).json()["scenario_id"]
    client.post("/apply", json={"scenario_id": sid, "action": "fans_off"})
    detect = client.post("/detect", json={"scenario_id": sid}).json()
    assert detect["detected"] is False
    assert detect["note"] == "fans off: smoke cannot reach vents"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/detect", {"scenario_id": "nope"}),
        ("post", "/suppress", {"scenario_id": "nope"}),
        ("post", "/chat", {"message": "hi", "scenario_id": "nope"}),
        ("get", "/results/nope", None),
        ("get", "/export/nope.pdf", None),
    ],
)
def test_unknown_scenario_is_404_everywhere(client, method, path, body) -> None:
    response = client.post(path, json=body) if method == "post" else client.get(path)
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_chat_without_a_scenario_still_answers(client) -> None:
    response = client.post("/chat", json={"message": "What did FLEX study?"})
    assert response.status_code == 200 and response.json()["answer"]


def test_full_loop_on_the_real_nasa_table(client, real_artifacts) -> None:
    table = model.load_table()
    assert not table["is_synthetic"].any(), "the committed table still contains synthetic rows"
    for material in ("Heptane", "PMMA rod"):
        out = _run_loop(client, {"material": material, "o2_pct": 21.0, "flow_speed_cm_s": 0.0})
        simulate = out["simulate"].json()
        assert 0.0 <= simulate["burn_probability"] <= 1.0
        assert all(not t["is_synthetic"] for t in simulate["nearest_tests"])
        assert all(
            t["source_url"].startswith("https://psi.nasa.gov") for t in simulate["nearest_tests"]
        )
        assert out["export"].content.startswith(b"%PDF")
