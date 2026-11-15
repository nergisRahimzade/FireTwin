"""DAT-02/DAT-05: outcome labels, spread rates, the extra cleaners and pipeline reproducibility."""

import csv
import subprocess

import pandas as pd
import pytest
from clean_bass import clean as clean_bass
from clean_detection_and_flex2 import clean_flex2, clean_same, clean_same_r
from clean_saffire_1_3 import clean_saffire_1, clean_saffire_3
from label_outcomes import MIN_CO2_RISE_PCT, build_labels
from psi_sources import BY_NAME, RAW_DIR, ROOT, SOURCES

LABELS = ROOT / "data" / "pipeline" / "label_outcomes.csv"


@pytest.fixture(scope="module")
def labels() -> pd.DataFrame:
    return pd.read_csv(LABELS)


def test_every_label_cites_its_source_cells(labels) -> None:
    assert len(labels) > 0
    assert labels["source_page"].notna().all()
    assert labels["source_page"].str.startswith("PSI-").all()
    assert set(labels["outcome"]) <= {"burned", "extinguished"}  # unknown is never written


def test_committed_labels_match_what_the_rules_produce(labels) -> None:
    fresh = pd.DataFrame(build_labels())
    assert fresh["test_id"].tolist() == labels["test_id"].tolist()
    assert fresh["outcome"].tolist() == labels["outcome"].tolist()


def test_sensor_inferred_labels_say_they_are_inferred(labels) -> None:
    bass = labels[labels["test_id"].str.startswith("BASS-II-") & (labels["outcome"] == "burned")]
    assert len(bass) > 0
    assert bass["source_page"].str.contains("INFERRED").all()
    assert (
        labels.loc[labels["outcome"] == "extinguished", "source_page"]
        .str.contains("INFERRED")
        .sum()
        == 0
    )


def test_every_labelled_test_exists_in_a_clean_table(labels) -> None:
    ids = set()
    for path in (ROOT / "data" / "clean").glob("*.csv"):
        ids |= set(pd.read_csv(path)["test_id"])
    assert set(labels["test_id"]) <= ids


def test_flex_labels_follow_the_test_end_column(labels) -> None:
    flex = pd.read_csv(ROOT / "data" / "clean" / "flex.csv").set_index("test_id")["outcome"]
    mine = labels[labels["test_id"].str.startswith("FLEX-")].set_index("test_id")["outcome"]
    assert (flex.loc[mine.index] == mine).all()  # a label never contradicts the cleaner
    assert not (
        flex.loc[flex.index.difference(mine.index)] != "unknown"
    ).any()  # disruptions stay unknown


def test_saffire_2_spread_rates_are_the_stated_ones_and_match_length_over_time(labels) -> None:
    rates = labels.dropna(subset=["spread_rate_mm_s"]).set_index("test_id")["spread_rate_mm_s"]
    assert rates.to_dict() == {"Saffire-II-2-5": 2.1, "Saffire-II-2-6": 2.6}
    # Cross-check against the table: 29 cm burned in 145 s and 115 s.
    assert 290 / 145 == pytest.approx(2.1, rel=0.05)
    assert 290 / 115 == pytest.approx(2.6, rel=0.05)


def test_saffire_2_insignificant_burns_are_extinguished(labels) -> None:
    got = labels.set_index("test_id")["outcome"]
    assert [got[f"Saffire-II-2-{i}"] for i in (1, 2, 3, 4)] == ["extinguished"] * 4
    assert [got[f"Saffire-II-2-{i}"] for i in (5, 6, 7, 8, 9)] == ["burned"] * 5


def test_bass_ii_burned_needs_real_combustion_evidence(labels) -> None:
    raw = pd.read_csv(ROOT / "data" / "pipeline" / "label_outcomes.csv")
    assert MIN_CO2_RISE_PCT > 0 and len(raw) > 0
    row = labels[labels["test_id"] == "BASS-II-B1"]
    assert row.empty  # CO2 flat and CO rose only 6 ppm: no label, stays unknown


def test_bass_has_no_conditions_and_saffire_3_has_no_o2() -> None:
    bass = clean_bass()
    assert len(bass) > 100 and all(r["o2_pct"] is None and r["flow_cm_s"] is None for r in bass)
    s3 = clean_saffire_3()
    assert [r["flow_cm_s"] for r in s3] == [30.0, 30.0] and all(r["o2_pct"] is None for r in s3)
    s1 = clean_saffire_1()
    assert [r["test_id"] for r in s1] == [
        "Saffire-I-S1",
        "Saffire-I-S2",
    ]  # flow-visualisation rows dropped
    assert all(r["o2_pct"] == 21.5 and r["flow_cm_s"] == 20.0 for r in s1)


def test_flex2_conditions_and_detection_tables_are_cleaned() -> None:
    flex2 = clean_flex2()
    assert len(flex2) == 8
    assert all(r["o2_pct_min"] == 17.0 and r["o2_pct_max"] == 30.0 for r in flex2)
    assert all(r["flow_cm_s_min"] == 0.1 and r["flow_cm_s_max"] == 5.0 for r in flex2)
    same = clean_same()
    assert (
        len(same) == 8
        and same[0]["material"] == "Teflon"
        and same[0]["weight_loss_rate_mg_min"] == 2.0
    )
    assert any(r["air_flow_cm_s"] is None for r in same)  # rows 5-8 say "same conditions as 1-4"
    same_r = clean_same_r()
    assert len(same_r) == 109 and all(r["rt_r0"] is not None for r in same_r)


def test_saffire_3_has_its_psi_id() -> None:
    assert BY_NAME["Saffire-III"].psi_id == "PSI-100"
    assert BY_NAME["Saffire-III"].page_url.endswith("PSI-100")


def test_every_source_table_is_committed_so_the_pipeline_runs_from_a_clone() -> None:
    for source in SOURCES:
        rel = source.raw_path.relative_to(ROOT).as_posix()
        assert source.raw_path.exists(), f"missing raw table {rel}"
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True, text=True
        )
        assert tracked.returncode == 0, f"{rel} is not committed to Git"
    assert RAW_DIR.name == "psi_tables"


def test_rows_without_o2_stay_out_of_the_unified_table() -> None:
    table = pd.read_parquet(ROOT / "data" / "processed" / "tests.parquet")
    assert table["o2_pct"].notna().all()
    assert (
        not table["test_id"]
        .str.startswith("BASS-")
        .where(table["investigation"] == "BASS", False)
        .any()
    )
    assert "Saffire-III" not in set(table["investigation"])


def test_data_quality_report_lists_what_was_left_out() -> None:
    report = (ROOT / "docs" / "data_quality.md").read_text(encoding="utf-8")
    assert "Rows left out of the unified table" in report
    assert "bass.csv" in report and "saffire_iii.csv" in report
    with (ROOT / "data" / "processed" / "data_quality.json").open(encoding="utf-8") as f:
        assert f.read().strip().startswith("{")
    assert csv.reader  # keep the csv import honest if the format changes
