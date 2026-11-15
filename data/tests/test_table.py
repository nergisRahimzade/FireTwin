"""DAT-08: checks on the committed unified table and the investigation summaries."""

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "data" / "processed" / "tests.parquet"
INVESTIGATIONS = ROOT / "data" / "processed" / "investigations.json"

COLUMNS = [
    "test_id",
    "investigation",
    "fuel_type",
    "material",
    "hardware",
    "o2_pct",
    "pressure_kpa",
    "flow_cm_s",
    "outcome",
    "spread_rate_mm_s",
    "source_url",
    "is_synthetic",
]
NUMERIC = ["o2_pct", "pressure_kpa", "flow_cm_s", "spread_rate_mm_s"]


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_parquet(TABLE)


def test_columns_are_the_unified_schema_in_order(table) -> None:
    assert list(table.columns) == COLUMNS


def test_column_types(table) -> None:
    for col in NUMERIC:
        assert pd.api.types.is_float_dtype(table[col]), f"{col} must be a float column"
    assert pd.api.types.is_bool_dtype(table["is_synthetic"])
    for col in ("test_id", "investigation", "fuel_type", "outcome", "source_url"):
        assert table[col].map(lambda v: isinstance(v, str)).all(), f"{col} must be text"


def test_oxygen_is_a_percentage(table) -> None:
    assert table["o2_pct"].dropna().between(0, 100).all()


def test_flow_and_pressure_are_not_negative(table) -> None:
    assert (table["flow_cm_s"].dropna() >= 0).all()
    assert (table["pressure_kpa"].dropna() > 0).all()


def test_no_duplicate_test_ids(table) -> None:
    duplicates = table.loc[table["test_id"].duplicated(), "test_id"].tolist()
    assert not duplicates, f"duplicate test_id values: {duplicates[:5]}"


def test_every_row_has_a_source_url(table) -> None:
    assert table["source_url"].str.strip().ne("").all()


def test_outcomes_and_fuel_types_use_the_allowed_words(table) -> None:
    assert set(table["outcome"]) <= {"burned", "extinguished", "unknown"}
    assert set(table["fuel_type"]) <= {"solid", "droplet", "gas"}


def test_real_rows_cite_nasa_psi(table) -> None:
    real = table[~table["is_synthetic"]]
    assert real["source_url"].str.startswith("https://psi.nasa.gov/").all()


def test_investigation_summaries_cover_every_investigation_in_the_table(table) -> None:
    summaries = json.loads(INVESTIGATIONS.read_text(encoding="utf-8"))
    names = {s["name"] for s in summaries}
    assert set(table["investigation"]) <= names
    assert {"SAME", "SAME-R"} <= names  # the detection pillar (DAT-06)
    for s in summaries:
        assert s["pillar"] in {"prevention", "detection", "suppression"}
        assert s["source_url"].startswith("https://psi.nasa.gov/")
        # A field with no source in the repo must be null AND listed as missing, never guessed.
        for key in s["missing"]:
            assert s[key] is None


def test_investigation_sensors_and_geometry_come_from_table_columns() -> None:
    summaries = {s["name"]: s for s in json.loads(INVESTIGATIONS.read_text(encoding="utf-8"))}
    assert "O2 gas analyzer" in summaries["BASS-II"]["sensors"]
    assert summaries["Saffire-II"]["sensors"] == ["video camera"]
    geometry = summaries["Saffire-II"]["sample_geometry"]
    assert geometry and not any("Burn" in key or "Spread" in key for key in geometry)
    assert summaries["BASS"]["sensors"] is None and "sensors" in summaries["BASS"]["missing"]
