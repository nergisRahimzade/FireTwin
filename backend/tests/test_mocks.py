"""BE-06 acceptance checks: all mock endpoints, synthetic labels, isolation and OpenAPI."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import schemas
from app.main import create_app
from app.services import store

SCENARIO_ID = "synthetic-scenario-001"
# Keys of a results row, in order: the plan's ResultsOut.rows keys, same as the BE-01 store.
ROW_KEYS = ["step", "inputs", "state", "probability", "trust", "detection_s", "action", "sources"]
SCENARIO = {"material": "Synthetic cotton", "o2_pct": 21, "flow_speed_cm_s": 10}
ENDPOINTS = [
    ("GET", "/health", None, schemas.HealthOut),
    ("GET", "/meta", None, schemas.MetaOut),
    ("POST", "/simulate", SCENARIO, schemas.SimulateOut),
    ("POST", "/detect", {"scenario_id": SCENARIO_ID}, schemas.DetectOut),
    ("POST", "/suppress", {"scenario_id": SCENARIO_ID}, schemas.SuppressOut),
    ("POST", "/apply", {"scenario_id": SCENARIO_ID, "action": "fans_off_co2"}, schemas.SimulateOut),
    ("GET", f"/results/{SCENARIO_ID}", None, schemas.ResultsOut),
    ("POST", "/chat", {"message": "Why?", "scenario_id": SCENARIO_ID}, schemas.ChatOut),
]
FEATURE_REQUESTS = [
    (method, path, body) for method, path, body, _ in ENDPOINTS if path != "/health"
]
FEATURE_REQUESTS.append(("GET", f"/export/{SCENARIO_ID}.pdf", None))
# Paths with a real router already: they exist with MOCK_MODE=0 too (see test_app_wiring.py).
REAL_PATHS = {"/meta", "/simulate", "/apply", "/detect"}
UNBUILT_REQUESTS = [request for request in FEATURE_REQUESTS if request[1] not in REAL_PATHS]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize("method,path,body,model", ENDPOINTS)
def test_mock_endpoint_matches_contract(client: TestClient, method, path, body, model) -> None:
    response = client.request(method, path, json=body)
    assert response.status_code == 200
    model.model_validate(response.json())


@pytest.mark.parametrize(
    "path,first,second",
    [
        ("/simulate", SCENARIO, {**SCENARIO, "o2_pct": 34, "flow_speed_cm_s": 0}),
        ("/detect", {"scenario_id": SCENARIO_ID}, {"scenario_id": "unknown"}),
        ("/suppress", {"scenario_id": SCENARIO_ID}, {"scenario_id": "unknown"}),
        (
            "/apply",
            {"scenario_id": SCENARIO_ID, "action": "fans_off_co2"},
            {"scenario_id": "unknown", "action": "water_mist"},
        ),
        ("/chat", {"message": "Why?"}, {"message": "Another question", "scenario_id": "unknown"}),
    ],
)
def test_mock_post_response_is_fixed(client: TestClient, path, first, second) -> None:
    assert client.post(path, json=first).json() == client.post(path, json=second).json()


def test_mock_results_ignore_unknown_scenario_id(client: TestClient) -> None:
    assert client.get("/results/unknown").json() == client.get(f"/results/{SCENARIO_ID}").json()


@pytest.mark.parametrize(
    "path,body",
    [
        ("/simulate", {}),
        ("/simulate", {**SCENARIO, "flow_dir": [1, 0]}),
        ("/detect", {}),
        ("/suppress", {}),
        ("/apply", {"scenario_id": SCENARIO_ID}),
        ("/apply", {"scenario_id": SCENARIO_ID, "action": "invalid"}),
        ("/chat", {}),
    ],
)
def test_mock_request_still_uses_contract_validation(client: TestClient, path, body) -> None:
    assert client.post(path, json=body).status_code == 422


def test_mock_loop_is_consistent_without_keys_or_artifacts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No data/model files exist in this cwd; no call depends on previous requests being stored.
    monkeypatch.chdir(tmp_path)
    meta = client.get("/meta").json()
    simulated = client.post("/simulate", json=SCENARIO).json()
    reference = {"scenario_id": simulated["scenario_id"]}
    detected = client.post("/detect", json=reference).json()
    suppressed = client.post("/suppress", json=reference).json()
    applied = client.post("/apply", json={**reference, "action": suppressed["recommended"]}).json()
    results = client.get(f"/results/{reference['scenario_id']}").json()
    assert meta["materials"][0]["name"] == simulated["inputs"]["material"]
    assert simulated["scenario_id"] == suppressed["scenario_id"] == applied["scenario_id"]
    assert results["scenario_id"] == simulated["scenario_id"]
    assert results["rows"][0]["state"] == simulated["state"] == "burning"
    assert results["rows"][-1]["state"] == applied["state"] == "extinguished"
    assert results["rows"][1]["detection_s"] == detected["time_to_detect_s"]
    assert results["rows"][-1]["action"] == suppressed["recommended"]
    assert results["rows"][-1]["inputs"] == applied["inputs"]
    assert client.get(f"/export/{reference['scenario_id']}.pdf").status_code == 200


def test_every_fixture_source_is_marked_synthetic(client: TestClient) -> None:
    def check_sources(value):
        if isinstance(value, dict):
            if "source_url" in value:
                assert value["is_synthetic"] is True
                assert value["source_url"] == "https://example.com"
            for nested in value.values():
                check_sources(nested)
        elif isinstance(value, list):
            for nested in value:
                check_sources(nested)

    for method, path, body, _ in ENDPOINTS:
        check_sources(client.request(method, path, json=body).json())


def test_freeform_numeric_fixtures_are_marked_synthetic(client: TestClient) -> None:
    meta = client.get("/meta").json()
    detected = client.post("/detect", json={"scenario_id": SCENARIO_ID}).json()
    entries = [
        *meta["materials"],
        *meta["ranges"].values(),
        *detected["detectors"],
    ]
    assert all(entry["is_synthetic"] is True for entry in entries)


def test_results_rows_match_store_shape(client: TestClient) -> None:
    rows = client.get(f"/results/{SCENARIO_ID}").json()["rows"]
    assert [list(row) for row in rows] == [ROW_KEYS] * len(rows)
    assert [row["step"] for row in rows] == ["simulate", "detect", "apply"]


def test_results_rows_equal_what_the_real_store_records(client: TestClient) -> None:
    # Record each mock row's values through the real store; the JSON must come out identical,
    # so the frontend sees the same shape in mock and real mode (BE-08 serves the real rows).
    rows = client.get(f"/results/{SCENARIO_ID}").json()["rows"]
    scenario_id = store.create(schemas.ScenarioIn(**rows[0]["inputs"]))
    for row in rows:
        values = {key: row[key] for key in ROW_KEYS if key not in ("step", "inputs")}
        inputs = schemas.ScenarioIn(**row["inputs"])
        store.append(scenario_id, row["step"], inputs=inputs, **values)
    assert json.loads(json.dumps(store.history(scenario_id))) == rows


def test_detect_row_has_only_the_detection_time(client: TestClient) -> None:
    detect_row = client.get(f"/results/{SCENARIO_ID}").json()["rows"][1]
    # Like the real store: a detect step makes no new verdict, so those values are None.
    assert detect_row["detection_s"] == 12.5
    assert detect_row["state"] is detect_row["probability"] is detect_row["trust"] is None


def test_results_row_sources_are_the_synthetic_tests(client: TestClient) -> None:
    # Rows hold test ids only; each id must be one of the synthetic TestRefs /simulate returns.
    synthetic_ids = {
        ref["test_id"]
        for ref in client.post("/simulate", json=SCENARIO).json()["nearest_tests"]
        if ref["is_synthetic"]
    }
    rows = client.get(f"/results/{SCENARIO_ID}").json()["rows"]
    assert all(row["sources"] and set(row["sources"]) <= synthetic_ids for row in rows)


@pytest.mark.parametrize("path", ["/simulate", "/apply"])
def test_simulated_verdict_does_not_claim_nasa_support(client: TestClient, path: str) -> None:
    body = SCENARIO if path == "/simulate" else {"scenario_id": SCENARIO_ID, "action": "co2"}
    verdict = client.post(path, json=body).json()
    assert verdict["explanation"].startswith("Synthetic mock:")
    assert verdict["trust"] == "weak"
    assert verdict["extrapolated"] is True
    assert len(verdict["nearest_tests"]) == 3
    assert all(source["is_synthetic"] is True for source in verdict["nearest_tests"])


def test_suppression_fixture_has_five_sorted_unsupported_actions(client: TestClient) -> None:
    result = client.post("/suppress", json={"scenario_id": SCENARIO_ID}).json()
    actions = result["actions"]
    assert {item["action"] for item in actions} == {
        "fans_off",
        "cut_power",
        "co2",
        "water_mist",
        "fans_off_co2",
    }
    assert [item["score"] for item in actions] == sorted(
        (item["score"] for item in actions), reverse=True
    )
    assert result["recommended"] == actions[0]["action"]
    assert all(item["data_support"] == "none" for item in actions)
    assert all(item["explanation"].startswith("Synthetic mock:") for item in actions)


def test_export_returns_valid_fixed_synthetic_pdf(client: TestClient) -> None:
    response = client.get(f"/export/{SCENARIO_ID}.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"] == 'attachment; filename="firetwin-synthetic.pdf"'
    )
    pdf = response.content
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert b"SYNTHETIC MOCK - NOT NASA DATA" in pdf
    assert b"is_synthetic=true" in pdf
    xref = re.search(rb"startxref\n(\d+)\n", pdf)
    assert xref is not None
    assert pdf[int(xref[1]) :].startswith(b"xref\n")
    assert pdf == client.get("/export/unknown.pdf").content


def test_docs_and_openapi_expose_every_contract_schema(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    specification = client.get("/openapi.json").json()
    assert "Synthetic mock API" in specification["info"]["description"]
    assert {
        "TestRef",
        "ScenarioIn",
        "SimulateOut",
        "DetectOut",
        "ActionResult",
        "SuppressOut",
        "ResultsOut",
        "ChatOut",
        "MetaOut",
        "ScenarioRef",
        "ApplyIn",
        "ChatIn",
        "HealthOut",
    } <= specification["components"]["schemas"].keys()
    assert set(specification["paths"]) == {
        "/health",
        "/meta",
        "/simulate",
        "/detect",
        "/suppress",
        "/apply",
        "/results/{scenario_id}",
        "/chat",
        "/export/{scenario_id}.pdf",
    }


def test_openapi_documents_pdf_instead_of_json(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/export/{scenario_id}.pdf"]["get"]
    assert set(operation["responses"]["200"]["content"]) == {"application/pdf"}


@pytest.mark.parametrize("method,path,body", UNBUILT_REQUESTS)
def test_unbuilt_routes_are_absent_when_mocks_disabled(
    monkeypatch: pytest.MonkeyPatch, method, path, body
) -> None:
    monkeypatch.setenv("MOCK_MODE", "0")
    with TestClient(create_app()) as client:
        assert client.request(method, path, json=body).status_code == 404


def test_health_remains_available_when_mocks_are_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "0")
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_mode_is_captured_per_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "1")
    mocked = create_app()
    monkeypatch.setenv("MOCK_MODE", "0")
    real = create_app()
    with TestClient(mocked) as mock_client, TestClient(real) as real_client:
        # /chat has no real router yet, so it only exists in the mocked app.
        assert mock_client.post("/chat", json={"message": "Why?"}).status_code == 200
        assert real_client.post("/chat", json={"message": "Why?"}).status_code == 404
