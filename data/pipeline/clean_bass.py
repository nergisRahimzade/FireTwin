"""DAT-05: clean the BASS table (PSI-26) into data/clean/bass.csv.

The BASS table lists the 122 fuel samples that were run (date, test and sample numbers, material)
and nothing else: it has no O2, flow or outcome columns. Those cells stay empty (never guessed),
so these rows are kept in the clean file but are left out of the unified burn-test table.
"""

from __future__ import annotations

from pathlib import Path

from psi_sources import BY_NAME, CLEAN_DIR, read_rows, write_clean

SOURCE = BY_NAME["BASS"]


def clean(raw_path: Path = SOURCE.raw_path) -> list[dict]:
    rows = []
    for r in read_rows(raw_path):
        test = r.get("Test #", "") or r.get("As Run Test #", "")
        material = " ".join(r.get("Fuel Sample Material", "").split())
        if not test or not material:
            continue  # blank line or a row with no test number
        rows.append(
            {
                "test_id": f"BASS-{test}",
                "investigation": SOURCE.name,
                "fuel_type": "solid",
                "material": material,
                "hardware": "MSG",
                "o2_pct": None,
                "pressure_kpa": None,
                "flow_cm_s": None,
                "outcome": "unknown",
                "spread_rate_mm_s": None,
                "source_url": SOURCE.page_url,
                "is_synthetic": False,
            }
        )
    return rows


def main() -> None:
    path = write_clean(clean(), CLEAN_DIR / "bass.csv")
    print(f"clean_bass: wrote {path}")


if __name__ == "__main__":
    main()
