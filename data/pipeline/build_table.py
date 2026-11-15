"""Build the unified test table data/processed/tests.parquet (DAT-01 seed, DAT-03 real merge).

If cleaned CSVs exist in data/clean/, they are merged with label_outcomes.csv (DAT-03).
If none exist yet, a clearly synthetic seed table is written instead (DAT-01): every seed
row has is_synthetic=True and a source_url that says it is not NASA data.
"""

from __future__ import annotations

import logging
import math
import random
from pathlib import Path

import pandas as pd

log = logging.getLogger("build_table")

ROOT = Path(__file__).resolve().parents[2]
CLEAN_DIR = ROOT / "data" / "clean"
LABELS_CSV = ROOT / "data" / "pipeline" / "label_outcomes.csv"
OUT_PARQUET = ROOT / "data" / "processed" / "tests.parquet"

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

SEED_SOURCE = "synthetic-seed (placeholder, not NASA data)"

# (investigation, fuel_type, material, hardware, a, u_star, c): a/u_star/c shape the fake
# U-shaped flammability boundary O2_crit(u) = a + c * (ln(u + 0.5) - ln(u_star))^2.
_SEED_GROUPS = [
    ("BASS-II", "solid", "PMMA", "MSG", 16.0, 10.0, 1.2),
    ("Saffire-II", "solid", "cable insulation", "Cygnus", 16.5, 10.0, 1.2),
    ("Saffire-III", "solid", "cotton-fiberglass", "Cygnus", 15.5, 10.0, 1.2),
    ("FLEX", "droplet", "heptane", "CIR-MDCA", 14.0, 6.0, 0.8),
]


def build_seed(rows_per_group: int = 16, seed: int = 7) -> pd.DataFrame:
    """Return a synthetic table in the final schema (DAT-01). Deterministic for a given seed."""
    rng = random.Random(seed)
    rows = []
    for inv, fuel, material, hardware, a, u_star, c in _SEED_GROUPS:
        for i in range(rows_per_group):
            o2 = round(rng.uniform(13.0, 25.0), 1)
            flow = 0.0 if i % 5 == 0 else round(rng.uniform(0.5, 30.0), 1)
            pressure = rng.choice([101.3, 101.3, 70.3])
            o2_crit = a + c * (math.log(flow + 0.5) - math.log(u_star)) ** 2
            burned = o2 + rng.gauss(0.0, 0.8) > o2_crit
            rows.append(
                {
                    "test_id": f"SYN-{inv}-{i:02d}",
                    "investigation": inv,
                    "fuel_type": fuel,
                    "material": material,
                    "hardware": hardware,
                    "o2_pct": o2,
                    "pressure_kpa": pressure,
                    "flow_cm_s": flow,
                    "outcome": "burned" if burned else "extinguished",
                    "spread_rate_mm_s": None,
                    "source_url": SEED_SOURCE,
                    "is_synthetic": True,
                }
            )
    return pd.DataFrame(rows, columns=COLUMNS)


def build_real(clean_dir: Path = CLEAN_DIR, labels_csv: Path = LABELS_CSV) -> pd.DataFrame:
    """Merge data/clean/*.csv with label_outcomes.csv into the final schema (DAT-03)."""
    frames = []
    for path in sorted(clean_dir.glob("*.csv")):
        try:
            frames.append(pd.read_csv(path))
        except Exception:
            log.exception("build_real: could not read clean CSV %s", path)
            raise
    table = pd.concat(frames, ignore_index=True)
    if "outcome" not in table:
        table["outcome"] = "unknown"
    if "spread_rate_mm_s" not in table:
        table["spread_rate_mm_s"] = float("nan")
    if labels_csv.exists():
        try:
            labels = pd.read_csv(labels_csv, dtype={"test_id": str})
            uncited = labels[labels["outcome"].isin(["burned", "extinguished"])]
            uncited = uncited[uncited["source_page"].isna()]
            if not uncited.empty:
                raise ValueError(
                    f"labels without a source_page (DAT-02): {uncited['test_id'].tolist()[:5]}"
                )
            labels = labels.drop_duplicates("test_id").set_index("test_id")
            # A label wins over whatever the clean CSV says; rows without a label keep theirs.
            ids = table["test_id"].astype(str)
            for col in ("outcome", "spread_rate_mm_s"):
                table[col] = ids.map(labels[col]).combine_first(table[col])
        except Exception:
            log.exception("build_real: could not merge labels from %s", labels_csv)
            raise
    table["outcome"] = table["outcome"].fillna("unknown")
    if "is_synthetic" not in table:
        table["is_synthetic"] = False
    missing = [c for c in COLUMNS if c not in table.columns]
    if missing:
        raise ValueError(f"build_real: clean CSVs are missing columns {missing}")
    if table["test_id"].duplicated().any():
        dupes = table.loc[table["test_id"].duplicated(), "test_id"].tolist()
        raise ValueError(f"build_real: duplicate test_id values {dupes[:5]}")
    return table[COLUMNS]


def write_table(table: pd.DataFrame, path: Path = OUT_PARQUET) -> None:
    """Save the unified table as parquet with stable column types."""
    try:
        table = table.copy()
        for col in ("o2_pct", "pressure_kpa", "flow_cm_s", "spread_rate_mm_s"):
            table[col] = pd.to_numeric(table[col], errors="coerce")
        table["is_synthetic"] = table["is_synthetic"].astype(bool)
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path, index=False)
    except Exception:
        log.exception("write_table: could not write %d rows to %s", len(table), path)
        raise


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    has_clean = any(CLEAN_DIR.glob("*.csv"))
    table = build_real() if has_clean else build_seed()
    if not has_clean:
        log.warning("no CSVs in data/clean/: writing the SYNTHETIC seed table (DAT-01)")
    write_table(table)
    log.info("wrote %d rows to %s", len(table), OUT_PARQUET)


if __name__ == "__main__":
    main()
