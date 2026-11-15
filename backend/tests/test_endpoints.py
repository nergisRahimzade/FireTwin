"""BE-12: every endpoint over HTTP, in mock mode (MOCK_MODE=1) and real mode (MOCK_MODE=0).

One place that answers "is every endpoint tested in both modes?". The detailed behaviour of
each endpoint lives in its own test file; this matrix checks status + contract shape for all of
them, and the coverage guard below fails if a mode serves a route this matrix doesn't list.
Requests go through FastAPI's TestClient (the httpx client API), no server and no network.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import schemas
from app.main import create_app

# (method, path template, request body builder or None, response model; None = PDF)
ENDPOINTS = [
    ("GET", "/health", None, schemas.HealthOut),
    ("GET", "/meta", None, schemas.MetaOut),
    ("POST", "/simulate", "scenario", schemas.SimulateOut),
    ("POST", "/preview", "scenario", schemas.PreviewOut),
    ("POST", "/detect", "ref", schemas.DetectOut),
    ("POST", "/suppress", "ref", schemas.SuppressOut),
    ("POST", "/apply", "apply", schemas.SimulateOut),
    ("GET", "/results/{scenario_id}", None, schemas.ResultsOut),
    ("POST", "/chat", "chat", schemas.ChatOut),
    ("GET", "/export/{scenario_id}.pdf", None, None),
]
# Endpoints that take a scenario id (in the path or the body); an unknown id must give 404.
NEEDS_SCENARIO = {
    "/chat",
    "/detect",
    "/suppress",
    "/apply",
    "/results/{scenario_id}",
    "/export/{scenario_id}.pdf",
}


def _client(monkeypatch: pytest.MonkeyPatch, mode: str) -> TestClient:
    monkeypatch.setenv("MOCK_MODE", mode)
    return TestClient(create_app())


def _material(client: TestClient) -> str:
    # The demo script's material if /meta offers it, else the first one: valid in both modes.
    names = [m["name"] for m in client.get("/meta").json()["materials"]]
    return "cable insulation" if "cable insulation" in names else names[0]


def _scenario_body(client: TestClient) -> dict:
    return {"material": _material(client), "o2_pct": 21, "flow_speed_cm_s": 10}


def _call(client: TestClient, method: str, template: str, body_kind: str | None, scenario_id: str):
    path = template.format(scenario_id=scenario_id)
    body = {
        None: None,
        "scenario": _scenario_body(client),
        "ref": {"scenario_id": scenario_id},
        "apply": {"scenario_id": scenario_id, "action": "fans_off"},
        "chat": {"message": "Why did fans off work?", "scenario_id": scenario_id},
    }[body_kind]
    return client.request(method, path, json=body)


def _cases():
    for mode in ("1", "0"):
        for method, path, body, model in ENDPOINTS:
            label = f"{'mock' if mode == '1' else 'real'}-{method}-{path}"
            yield pytest.param(mode, method, path, body, model, id=label)


@pytest.mark.parametrize("mode,method,path,body,model", list(_cases()))
def test_endpoint_answers_with_its_contract(
    monkeypatch: pytest.MonkeyPatch, mode, method, path, body, model: type[BaseModel] | None
) -> None:
    client = _client(monkeypatch, mode)
    scenario_id = client.post("/simulate", json=_scenario_body(client)).json()["scenario_id"]
    response = _call(client, method, path, body, scenario_id)
    assert response.status_code == 200, response.text[:300]
    if model is None:  # the PDF export
        assert response.headers["content-type"].startswith("application/pdf")
        assert response.content.startswith(b"%PDF")
    else:
        model.model_validate(response.json())


@pytest.mark.parametrize("mode", ["1", "0"], ids=["mock", "real"])
def test_every_served_route_is_in_the_matrix(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    # A new endpoint must get a row in ENDPOINTS (and so a test in both modes).
    served = set(_client(monkeypatch, mode).get("/openapi.json").json()["paths"])
    assert served == {path for _, path, _, _ in ENDPOINTS}


@pytest.mark.parametrize("template", sorted(NEEDS_SCENARIO))
def test_real_mode_unknown_scenario_is_404(monkeypatch: pytest.MonkeyPatch, template: str) -> None:
    method, _, body, _ = next(e for e in ENDPOINTS if e[1] == template)
    response = _call(_client(monkeypatch, "0"), method, template, body, "never-created")
    assert response.status_code == 404


def test_fans_off_ranks_above_water_mist_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Plan BE-12: "fans_off beats water_mist with default data", here through the real API.
    client = _client(monkeypatch, "0")
    scenario_id = client.post("/simulate", json=_scenario_body(client)).json()["scenario_id"]
    ranked = client.post("/suppress", json={"scenario_id": scenario_id}).json()["actions"]
    order = [action["action"] for action in ranked]
    assert order.index("fans_off") < order.index("water_mist")


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "OPENAI_API_KEY"])
def test_no_llm_key_reaches_a_test(name: str) -> None:
    # conftest.py clears these, so a key in a developer's shell can't cause real (billed) API calls.
    import os

    assert name not in os.environ
