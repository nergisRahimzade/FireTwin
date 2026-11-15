"""DAT-01: the unified table loads in pandas and has the final schema."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
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


def test_table_schema() -> None:
    table = pd.read_parquet(ROOT / "data" / "processed" / "tests.parquet")
    assert list(table.columns) == COLUMNS
    assert len(table) >= 40
    assert not table["test_id"].duplicated().any()
    # A value may be missing (the NASA table did not report it); a present one must be valid.
    assert table["o2_pct"].dropna().between(0, 100).all()
    assert (table["flow_cm_s"].dropna() >= 0).all()
    assert set(table["outcome"]) <= {"burned", "extinguished", "unknown"}
    assert table["source_url"].str.len().gt(0).all()
    assert set(table["fuel_type"]) <= {"solid", "droplet", "gas"}
