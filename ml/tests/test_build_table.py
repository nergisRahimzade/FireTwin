"""DAT-02 / DAT-03: clean CSVs + outcome labels merge into the unified schema."""

from pathlib import Path

import pandas as pd
import pytest

from data.pipeline import build_table

CLEAN = (
    "test_id,investigation,fuel_type,material,hardware,o2_pct,pressure_kpa,flow_cm_s,source_url\n"
    "T1,BASS-II,solid,PMMA,MSG,21.0,101.3,10.0,https://example.test/bass\n"
    "T2,BASS-II,solid,PMMA,MSG,17.0,101.3,0.0,https://example.test/bass\n"
    "T3,BASS-II,solid,PMMA,MSG,19.0,101.3,5.0,https://example.test/bass\n"
)


def _write(tmp_path: Path, labels: str) -> tuple[Path, Path]:
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    (clean_dir / "bass2.csv").write_text(CLEAN)
    labels_csv = tmp_path / "label_outcomes.csv"
    labels_csv.write_text("test_id,outcome,spread_rate_mm_s,source_page\n" + labels)
    return clean_dir, labels_csv


def test_labels_are_merged_and_unlabeled_rows_stay_unknown(tmp_path: Path) -> None:
    clean_dir, labels_csv = _write(tmp_path, "T1,burned,1.5,p. 12\nT2,extinguished,,p. 14\n")
    table = build_table.build_real(clean_dir, labels_csv).set_index("test_id")
    assert list(table.reset_index().columns) == build_table.COLUMNS
    assert table.loc["T1", "outcome"] == "burned"
    assert table.loc["T1", "spread_rate_mm_s"] == 1.5
    assert table.loc["T2", "outcome"] == "extinguished"
    assert table.loc["T3", "outcome"] == "unknown"
    assert not table["is_synthetic"].any()


def test_label_without_source_page_is_rejected(tmp_path: Path) -> None:
    clean_dir, labels_csv = _write(tmp_path, "T1,burned,1.5,\n")
    with pytest.raises(ValueError, match="source_page"):
        build_table.build_real(clean_dir, labels_csv)


def test_duplicate_test_ids_are_rejected(tmp_path: Path) -> None:
    clean_dir, labels_csv = _write(tmp_path, "")
    (clean_dir / "copy.csv").write_text(CLEAN)
    with pytest.raises(ValueError, match="duplicate"):
        build_table.build_real(clean_dir, labels_csv)


def test_committed_labels_file_has_the_dat02_columns() -> None:
    labels = pd.read_csv(build_table.LABELS_CSV)
    assert list(labels.columns) == ["test_id", "outcome", "spread_rate_mm_s", "source_page"]
    labeled = labels[labels["outcome"].isin(["burned", "extinguished"])]
    assert labeled["source_page"].notna().all()
