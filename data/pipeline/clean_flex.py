"""DAT-05: clean the FLEX table (PSI-69) into data/clean/flex.csv.

One row per droplet burn. O2 is a mole fraction in PSI (x100 -> o2_pct), pressure is mmHg
(-> kPa). FLEX droplets burned in still gas inside the chamber, so flow_cm_s is 0. The table's
own "Test end" column gives the outcome: Completion -> burned (it burned until the fuel was
gone), Extinction -> extinguished, Disruption (the droplet broke up) -> unknown.
"""

from __future__ import annotations

from pathlib import Path

from psi_sources import (
    BY_NAME,
    CLEAN_DIR,
    MMHG_TO_KPA,
    first_number,
    read_rows,
    rounded,
    write_clean,
)

SOURCE = BY_NAME["FLEX"]
OUTCOMES = {"completion": "burned", "extinction": "extinguished", "disruption": "unknown"}


def clean(raw_path: Path = SOURCE.raw_path) -> list[dict]:
    rows = []
    for r in read_rows(raw_path):
        test_no = r.get("FLEX Test #", "")
        if not test_no:
            continue  # empty or footnote rows
        mole_fraction = first_number(r.get("O initial ambient composition; mole fraction"))
        mmhg = first_number(r.get("Ambient pressure; mmHg"))
        rows.append(
            {
                "test_id": f"FLEX-{test_no}",
                "investigation": SOURCE.name,
                "fuel_type": "droplet",
                "material": r["Fuel"],
                "hardware": "CIR-MDCA",
                "o2_pct": rounded(mole_fraction * 100 if mole_fraction is not None else None),
                "pressure_kpa": rounded(mmhg * MMHG_TO_KPA if mmhg else None),  # 0 = not recorded
                "flow_cm_s": 0.0,
                "outcome": OUTCOMES.get(r.get("Test end", "").strip().lower(), "unknown"),
                "spread_rate_mm_s": None,
                "source_url": SOURCE.page_url,
                "is_synthetic": False,
            }
        )
    return rows


def main() -> None:
    path = write_clean(clean(), CLEAN_DIR / "flex.csv")
    print(f"clean_flex: wrote {path}")


if __name__ == "__main__":
    main()
