"""BE-09: real PDF content, history parity, offline operation, pagination and mode wiring."""

import re
from datetime import UTC, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ActionResult, ResultsOut, ScenarioIn, SuppressOut, TestRef
from app.services import pdf, store, suppressor
from ml.pipeline import model

BURN_PROBABILITY = 0.8123456789123456
AFTER_PROBABILITY = 0.12345678912345678

INPUTS = ScenarioIn(material="Synthetic cotton", o2_pct=21, flow_speed_cm_s=10)
SOURCE = TestRef(
    test_id="synthetic-export-001",
    investigation="Synthetic export fixture",
    fuel_type="solid",
    o2_pct=21,
    pressure_kpa=101.3,
    flow_cm_s=10,
    outcome="burned",
    source_url="https://example.com/synthetic-export-source",
    is_synthetic=True,
)


def _recommendation(scenario_id: str, inputs: ScenarioIn) -> SuppressOut:
    return SuppressOut(
        scenario_id=scenario_id,
        recommended="fans_off",
        actions=[
            ActionResult(
                action="fans_off",
                label="Fans off",
                new_inputs=inputs,
                extinction_probability=0.8,
                crew_risk=0.1,
                score=0.75,
                data_support="indirect",
                sources=[SOURCE],
                explanation="Synthetic recommendation.",
            )
        ],
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setattr(suppressor, "suppress", _recommendation)
    monkeypatch.setattr(model, "load_table", lambda: pd.DataFrame([SOURCE.model_dump()]))
    store.clear()
    with TestClient(create_app()) as client:
        yield client
    store.clear()


def _recorded_scenario() -> str:
    scenario_id = store.create(INPUTS)
    store.append(
        scenario_id,
        "simulate",
        state="burning",
        probability=BURN_PROBABILITY,
        trust="weak",
        sources=[SOURCE.test_id],
    )
    store.append(scenario_id, "detect", detection_s=0)
    store.append(
        scenario_id,
        "apply",
        inputs=INPUTS.model_copy(update={"flow_speed_cm_s": 0}),
        state="extinguished",
        probability=AFTER_PROBABILITY,
        action="fans_off",
        sources=[SOURCE.test_id],
    )
    return scenario_id


def test_export_downloads_a_real_pdf(client: TestClient) -> None:
    response = client.get(f"/export/{_recorded_scenario()}.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="firetwin-results.pdf"'
    assert response.content.startswith(b"%PDF-")
    assert response.content.rstrip().endswith(b"%%EOF")
    assert b"/Type /Page" in response.content


def test_export_contains_required_report_sections(client: TestClient) -> None:
    scenario_id = _recorded_scenario()
    content = client.get(f"/export/{scenario_id}.pdf").content
    for value in [
        b"FireTwin scenario report",
        scenario_id.encode(),
        b"Generated at",
        b"Current scenario inputs",
        b"Synthetic cotton",
        b"Recorded results",
        b"Recommended action",
        b"Fans off",
        b"Sources with URLs",
        SOURCE.source_url.encode(),
        pdf.HONESTY_LINE.encode(),
    ]:
        assert value in content


def test_report_uses_requested_utc_timestamp() -> None:
    content = pdf.render_report(
        ResultsOut(scenario_id="synthetic-id", rows=[]),
        INPUTS,
        None,
        [],
        generated_at=datetime(2026, 11, 14, 12, 34, 56, tzinfo=UTC),
    )
    assert b"2026-11-14T12:34:56+00:00" in content


def test_export_passes_exact_results_rows_to_renderer(client: TestClient, monkeypatch) -> None:
    scenario_id = _recorded_scenario()
    expected = client.get(f"/results/{scenario_id}").json()
    received = []
    original = pdf.render_report

    def capture(results, *args, **kwargs):
        received.append(results.model_dump(mode="json"))
        return original(results, *args, **kwargs)

    monkeypatch.setattr(pdf, "render_report", capture)
    assert client.get(f"/export/{scenario_id}.pdf").status_code == 200
    assert received == [expected]


def test_export_preserves_numeric_precision_and_nulls(client: TestClient) -> None:
    content = client.get(f"/export/{_recorded_scenario()}.pdf").content
    assert str(BURN_PROBABILITY).encode() in content
    assert str(AFTER_PROBABILITY).encode() in content
    assert b"(null) Tj" in content
    assert b"(0) Tj" in content  # Detection at zero seconds must not look like null.
    assert content.index(b'("simulate")') < content.index(b'("detect")')
    assert content.index(b'("detect")') < content.index(b'("apply")')


def test_export_labels_synthetic_evidence(client: TestClient) -> None:
    content = client.get(f"/export/{_recorded_scenario()}.pdf").content
    assert b"SYNTHETIC DATA" in content
    assert b"is_synthetic=true" in content


def test_export_does_not_change_scenario_or_append_history(client: TestClient) -> None:
    scenario_id = _recorded_scenario()
    before = store.get(scenario_id)
    assert client.get(f"/export/{scenario_id}.pdf").status_code == 200
    assert client.get(f"/export/{scenario_id}.pdf").status_code == 200
    assert store.get(scenario_id) == before


def test_unknown_scenario_is_404(client: TestClient) -> None:
    response = client.get("/export/unknown.pdf")
    assert response.status_code == 404
    assert "unknown" in response.json()["detail"]


def test_unknown_scenario_does_not_calculate_recommendation(
    client: TestClient, monkeypatch
) -> None:
    def fail(*args):
        pytest.fail("Unknown IDs must not invoke the ranker")

    monkeypatch.setattr(suppressor, "suppress", fail)
    assert client.get("/export/unknown.pdf").status_code == 404


def test_existing_scenario_with_empty_history_has_an_empty_report(client: TestClient) -> None:
    content = client.get(f"/export/{store.create(INPUTS)}.pdf").content
    assert b"No recorded steps." in content


def test_export_marks_new_recommendation_as_export_time_calculation(client: TestClient) -> None:
    content = client.get(f"/export/{_recorded_scenario()}.pdf").content
    assert b"Calculated at export time" in content
    assert b"not a recorded history step" in content
    assert b"illustrative crew-risk" in content


def test_missing_model_still_exports_history(client: TestClient, monkeypatch) -> None:
    def missing(*args):
        raise FileNotFoundError("model.joblib")

    monkeypatch.setattr(suppressor, "suppress", missing)
    response = client.get(f"/export/{_recorded_scenario()}.pdf")
    assert response.status_code == 200
    assert b"Unavailable: model or data not available" in response.content
    assert str(BURN_PROBABILITY).encode() in response.content


def test_missing_source_id_has_no_invented_url(client: TestClient) -> None:
    scenario_id = store.create(INPUTS)
    store.append(scenario_id, "simulate", sources=["missing-test-id"])
    content = client.get(f"/export/{scenario_id}.pdf").content
    assert b"missing-test-id" in content
    assert b"UNVERIFIED" in content
    assert b"synthetic status unknown" in content


def test_missing_table_still_exports_unverified_history(client: TestClient, monkeypatch) -> None:
    def missing():
        raise FileNotFoundError("tests.parquet")

    monkeypatch.setattr(model, "load_table", missing)
    scenario_id = store.create(INPUTS)
    store.append(scenario_id, "simulate", sources=["historical-test-id"])
    response = client.get(f"/export/{scenario_id}.pdf")
    assert response.status_code == 200
    assert b"historical-test-id" in response.content
    assert b"UNVERIFIED" in response.content


def test_report_escapes_material_and_source_markup(client: TestClient, monkeypatch) -> None:
    def fail(*args, **kwargs):
        pytest.fail("Escaped user text must never load images")

    monkeypatch.setattr("reportlab.platypus.paraparser.ImageReader", fail)
    bad = '<b>synthetic</b> & <img src="https://example.com/never-fetch"/>'
    scenario_id = store.create(INPUTS.model_copy(update={"material": bad}))
    store.append(scenario_id, "simulate", sources=["synthetic-markup"])
    ref = SOURCE.model_copy(update={"test_id": "synthetic-markup", "source_url": bad})
    monkeypatch.setattr(model, "load_table", lambda: pd.DataFrame([ref.model_dump()]))
    response = client.get(f"/export/{scenario_id}.pdf")
    assert response.status_code == 200
    # Text is printed literally: it cannot invoke ReportLab's image loader.
    assert b"never-fetch" in response.content
    assert b"/Subtype /Image" not in response.content


def test_large_history_paginates_and_keeps_last_row(client: TestClient) -> None:
    scenario_id = store.create(INPUTS)
    for index in range(70):
        store.append(scenario_id, "simulate", sources=[f"synthetic-page-test-{index:03d}"])
    response = client.get(f"/export/{scenario_id}.pdf")
    assert response.status_code == 200
    assert len(re.findall(rb"/Type /Page\b", response.content)) > 1
    assert b"synthetic-page-test-069" in response.content


def test_export_openapi_advertises_pdf(client: TestClient) -> None:
    op = client.get("/openapi.json").json()["paths"]["/export/{scenario_id}.pdf"]["get"]
    assert set(op["responses"]["200"]["content"]) == {"application/pdf"}
    assert "404" in op["responses"]


def test_mock_export_does_not_call_real_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args):
        pytest.fail("Mock mode must use the existing static fixture")

    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setattr(pdf, "export_scenario", fail)
    with TestClient(create_app()) as client:
        response = client.get("/export/any-id.pdf")
    assert response.status_code == 200
    assert (
        response.headers["content-disposition"] == 'attachment; filename="firetwin-synthetic.pdf"'
    )


def test_export_only_contains_the_requested_scenario(client: TestClient) -> None:
    first = _recorded_scenario()
    second = store.create(INPUTS.model_copy(update={"material": "Other unique synthetic material"}))
    store.append(second, "simulate")
    content = client.get(f"/export/{first}.pdf").content
    assert first.encode() in content
    assert second.encode() not in content
    assert b"Other unique synthetic material" not in content


def test_single_long_history_row_splits_across_pages(client: TestClient) -> None:
    material = "Synthetic long material " * 500 + "END_OF_MATERIAL"
    scenario_id = store.create(INPUTS.model_copy(update={"material": material}))
    store.append(scenario_id, "simulate", probability=AFTER_PROBABILITY)
    response = client.get(f"/export/{scenario_id}.pdf")
    assert response.status_code == 200
    assert len(re.findall(rb"/Type /Page\b", response.content)) > 1
    # Summary and history both retain the complete material, even when a row exceeds a page.
    assert response.content.count(b"END_OF_MATERIAL") == 2
    assert str(AFTER_PROBABILITY).encode() in response.content
