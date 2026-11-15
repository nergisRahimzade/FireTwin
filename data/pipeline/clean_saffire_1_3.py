"""DAT-05: clean the Saffire-I (PSI-98) and Saffire-III (PSI-100) tables into data/clean/.

Saffire-I: samples S1 and S2 (SIBAL cotton-fiberglass fabric, 20 cm/s, O2 ~21.5 %). The two
"F1C1/F1C2" rows are pre-test flow-visualisation recordings, not burns, so they are dropped.
Saffire-III: samples S1 and S2 (SIBAL fabric, 30 cm/s). The table records no O2 and no outcome,
so those cells stay empty and the rows are kept out of the unified burn-test table.
Outcomes and spread rates are filled in later by label_outcomes.py, never here.
"""

from __future__ import annotations

import re
from pathlib import Path

from psi_sources import BY_NAME, CLEAN_DIR, first_number, flow_cm_s, read_rows, rounded, write_clean

SAMPLE = re.compile(r"^S\d+$")


def _rows(name: str, flow_col: str, o2_col: str | None, prefix: str) -> list[dict]:
    source = BY_NAME[name]
    rows = []
    for r in read_rows(source.raw_path):
        sample = r.get("Sample Number", "")
        if not SAMPLE.match(sample):
            continue  # flow-visualisation recordings and footnotes
        rows.append(
            {
                "test_id": f"{prefix}-{sample}",
                "investigation": name,
                "fuel_type": "solid",
                "material": " ".join(r.get("Material", "").split()) or "unspecified",
                "hardware": "Cygnus",
                "o2_pct": rounded(first_number(r.get(o2_col))) if o2_col else None,
                "pressure_kpa": None,
                "flow_cm_s": rounded(flow_cm_s(r.get(flow_col))),
                "outcome": "unknown",
                "spread_rate_mm_s": None,
                "source_url": source.page_url,
                "is_synthetic": False,
            }
        )
    return rows


def clean_saffire_1(raw_path: Path | None = None) -> list[dict]:
    return _rows("Saffire-I", "Air Flow (cm/s)", "Percent O2", "Saffire-I")


def clean_saffire_3(raw_path: Path | None = None) -> list[dict]:
    return _rows("Saffire-III", "Air Flow", None, "Saffire-III")


def main() -> None:
    for rows, name in (
        (clean_saffire_1(), "saffire_i.csv"),
        (clean_saffire_3(), "saffire_iii.csv"),
    ):
        print(f"clean_saffire_1_3: wrote {write_clean(rows, CLEAN_DIR / name)}")


if __name__ == "__main__":
    main()
