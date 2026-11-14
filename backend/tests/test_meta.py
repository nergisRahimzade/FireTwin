"""Tests for GET /meta (BE-07): service logic on small fixtures, plus the real seed files."""

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import meta as meta_router
from app.schemas import MetaOut, ScenarioIn
from app.services import meta, predictor
from ml.pipeline import model

RANGES = {
    "overall": {
        "o2_pct": {"min": 13.0, "max": 24.5},
        "pressure_kpa": {"min": 70.3, "max": 101.3},
        "flow_cm_s": {"min": 0.0, "max": 29.8},
    },
    "by_fuel_type": {},
}


def _table(*rows: tuple[str | None, str, bool]) -> pd.DataFrame:
    # (material, fuel_type, is_synthetic) per test row; other columns don't matter to /meta.
    return pd.DataFrame(rows, columns=["material", "fuel_type", "is_synthetic"])


@pytest.fixture
def fake_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point the service at a small table, the RANGES above, and no investigations.json."""

    def use(table: pd.DataFrame, ranges: dict = RANGES) -> None:
        monkeypatch.setattr(model, "load_table", lambda: table)
        monkeypatch.setattr(model, "load_ranges", lambda: ranges)

    monkeypatch.setattr(meta, "INVESTIGATIONS_PATH", tmp_path / "investigations.json")
    return use


def _client() -> TestClient:
    # Mounted the same way as the simulate router's tests; main.py wiring is a separate step.
    app = FastAPI()
    app.include_router(meta_router.router)
    return TestClient(app)


# --- service, with small fixtures ---


def test_materials_count_tests_per_material(fake_data) -> None:
    fake_data(
        _table(("PMMA", "solid", False), ("PMMA", "solid", False), ("heptane", "droplet", False))
    )
    assert meta.build_meta().materials == [
        {"name": "PMMA", "fuel_type": "solid", "n_tests": 2, "is_synthetic": False},
        {"name": "heptane", "fuel_type": "droplet", "n_tests": 1, "is_synthetic": False},
    ]


def test_material_is_synthetic_if_any_of_its_tests_is(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False), ("PMMA", "solid", True)))
    assert meta.build_meta().materials[0]["is_synthetic"] is True


def test_rows_without_material_are_skipped(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False), (None, "solid", False)))
    assert [m["name"] for m in meta.build_meta().materials] == ["PMMA"]


def test_ranges_are_the_overall_section_per_feature(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False)))
    assert meta.build_meta().ranges == {
        "o2_pct": {"min": 13.0, "max": 24.5, "is_synthetic": False},
        "pressure_kpa": {"min": 70.3, "max": 101.3, "is_synthetic": False},
        "flow_cm_s": {"min": 0.0, "max": 29.8, "is_synthetic": False},
    }


def test_ranges_are_synthetic_if_any_table_row_is(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False), ("heptane", "droplet", True)))
    assert all(entry["is_synthetic"] for entry in meta.build_meta().ranges.values())


def test_missing_overall_ranges_raise(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False)), ranges={"by_fuel_type": {}})
    with pytest.raises(meta.MetaUnavailableError, match="overall"):
        meta.build_meta()


def test_missing_feature_range_raises(fake_data) -> None:
    broken = {"overall": {**RANGES["overall"], "flow_cm_s": {"min": 0.0}}}
    fake_data(_table(("PMMA", "solid", False)), ranges=broken)
    with pytest.raises(meta.MetaUnavailableError, match="flow_cm_s"):
        meta.build_meta()


def test_unreadable_table_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> pd.DataFrame:
        raise FileNotFoundError("tests.parquet")

    monkeypatch.setattr(model, "load_table", missing)
    with pytest.raises(meta.MetaUnavailableError, match="make data"):
        meta.build_meta()


def test_investigations_empty_without_file(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False)))
    assert meta.build_meta().investigations == []


def test_investigations_read_from_file(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False)))
    entries = [{"name": "FLEX", "pillar": "suppression", "is_synthetic": False}]
    meta.INVESTIGATIONS_PATH.write_text(json.dumps(entries))
    assert meta.build_meta().investigations == entries


def test_investigations_must_be_a_list_of_objects(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False)))
    meta.INVESTIGATIONS_PATH.write_text(json.dumps({"name": "FLEX"}))
    with pytest.raises(meta.MetaUnavailableError, match="list of objects"):
        meta.build_meta()


def test_result_is_plain_json(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False)))
    # numpy integers or booleans in the dicts would make this raise.
    json.dumps(meta.build_meta().model_dump())


# --- router ---


def test_get_meta_returns_contract_shape(fake_data) -> None:
    fake_data(_table(("PMMA", "solid", False)))
    response = _client().get("/meta")
    assert response.status_code == 200
    MetaOut.model_validate(response.json())


def test_get_meta_is_503_when_data_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> pd.DataFrame:
        raise FileNotFoundError("tests.parquet")

    monkeypatch.setattr(model, "load_table", missing)
    response = _client().get("/meta")
    assert response.status_code == 503
    assert "make data" in response.json()["detail"]


# --- the real seed files in the repo ---


def test_real_meta_lists_every_table_material() -> None:
    table = model.load_table()
    names = {m["name"] for m in meta.build_meta().materials}
    assert names == set(table["material"].dropna())


def test_real_meta_counts_add_up_to_table_rows() -> None:
    table = model.load_table()
    total = sum(m["n_tests"] for m in meta.build_meta().materials)
    assert total == table["material"].notna().sum()


def test_real_ranges_match_the_predictors_ranges_file() -> None:
    overall = model.load_ranges()["overall"]
    for feature, entry in meta.build_meta().ranges.items():
        assert (entry["min"], entry["max"]) == (overall[feature]["min"], overall[feature]["max"])


def test_real_materials_are_accepted_by_the_predictor() -> None:
    # The UI sends /meta's material names back to /simulate, so each must be known there.
    for material in meta.build_meta().materials:
        inputs = ScenarioIn(material=material["name"], o2_pct=21, flow_speed_cm_s=10)
        probability = predictor.predict(inputs)[0]
        assert 0.0 <= probability <= 1.0
