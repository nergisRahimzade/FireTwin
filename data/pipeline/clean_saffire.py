"""DAT-05: clean the Saffire tables into data/clean/saffire_ii.csv.

Saffire-II (PSI-99) only: no Saffire-III table has been found on PSI yet (see download.py).

One row per burned sample (2-1 to 2-9); flow-visualization rows and footnotes are dropped.
O2 is "~ 21.5" or "22.1 to 22.0" (the starting value is kept); airflow is "20 cm/s". The table
gives no cabin pressure and no single outcome per sample, so those stay empty / unknown.
Two samples have no material written in the PSI table; they say "unspecified".
"""

from __future__ import annotations

import re
from pathlib import Path

from psi_sources import BY_NAME, CLEAN_DIR, first_number, flow_cm_s, read_rows, rounded, write_clean

SOURCE = BY_NAME["Saffire-II"]
SAMPLE_ID = re.compile(r"^2-\d+$")


def clean(raw_path: Path = SOURCE.raw_path) -> list[dict]:
    rows = []
    for r in read_rows(raw_path):
        sample = r.get("Sample Number", "")
        if not SAMPLE_ID.match(sample):
            continue
        rows.append(
            {
                "test_id": f"Saffire-II-{sample}",
                "investigation": SOURCE.name,
                "fuel_type": "solid",
                "material": " ".join(r.get("Material", "").split()) or "unspecified",
                "hardware": "Cygnus",
                "o2_pct": rounded(first_number(r.get("Percent O2 (Note 1)"))),
                "pressure_kpa": None,
                "flow_cm_s": rounded(flow_cm_s(r.get("Air Flow (cm/s)"))),
                "outcome": "unknown",
                "spread_rate_mm_s": None,
                "source_url": SOURCE.page_url,
                "is_synthetic": False,
            }
        )
    return rows


def main() -> None:
    path = write_clean(clean(), CLEAN_DIR / "saffire_ii.csv")
    print(f"clean_saffire: wrote {path}")


if __name__ == "__main__":
    main()
