"""DAT-05: clean the tables that are not burn tests, into data/clean/other/.

- FLEX-2 (PSI-68): a matrix of planned conditions per fuel (ranges such as "0.17; 0.21; 0.25"),
  one row per fuel. Kept as one row per fuel, with every range written as min/max.
- SAME (PSI-102) and SAME-R (PSI-101): smoke-detection studies (aging time, weight-loss rate,
  inlet velocity, Rt/R0). They measure smoke, not whether a fire keeps burning, so they feed the
  detection pillar's documents and summaries and stay out of the burn-model table.
Empty cells stay empty; "n/a" is written as empty.
"""

from __future__ import annotations

import csv
from pathlib import Path

from psi_sources import BY_NAME, OTHER_DIR, first_number, numbers_in, read_rows


def _write(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _span(text: str) -> tuple[float | None, float | None]:
    values = numbers_in(text)
    return (min(values), max(values)) if values else (None, None)


def clean_flex2() -> list[dict]:
    source = BY_NAME["FLEX-2"]
    rows = []
    for r in read_rows(source.raw_path):
        fuel = r.get("Sample (Fuel Type)", "")
        if not fuel:
            continue
        o2_lo, o2_hi = _span(r.get("Oxygen Mole Fraction", ""))
        p_lo, p_hi = _span(r.get("Ambient Pressure (atm)", ""))
        f_lo, f_hi = _span(r.get("Flow Velocity (cm/s)", ""))
        d_lo, d_hi = _span(r.get("Initial Droplet Diameter (mm)", ""))
        rows.append(
            {
                "fuel": fuel,
                "o2_pct_min": None if o2_lo is None else round(o2_lo * 100, 2),
                "o2_pct_max": None if o2_hi is None else round(o2_hi * 100, 2),
                "pressure_atm_min": p_lo,
                "pressure_atm_max": p_hi,
                "flow_cm_s_min": f_lo,
                "flow_cm_s_max": f_hi,
                "droplet_diameter_mm_min": d_lo,
                "droplet_diameter_mm_max": d_hi,
                "ambient_gas": r.get("Ambient Gas Mixture", ""),
                "source_url": source.page_url,
            }
        )
    return rows


def _clean_cell(value: str) -> str:
    value = " ".join(value.split())
    return "" if value.lower() in {"n/a", "na", "none"} else value


def clean_same() -> list[dict]:
    source = BY_NAME["SAME"]
    rows = []
    for r in read_rows(source.raw_path):
        number = r.get("Sample #", "")
        if not number:
            continue
        material = _clean_cell(r.get("Sample Material", ""))
        rows.append(
            {
                "sample": number,
                "material": material.split(":")[0].strip(),
                "same_conditions_as_samples_1_4": "same condition" in material.lower(),
                "air_flow_cm_s": first_number(r.get("Air Flow (cm/s)")),
                "weight_loss_rate_mg_min": first_number(r.get("Weight loss rate (mg/min)")),
                "aging_duration_min": first_number(r.get("Aging Duration (minutes)")),
                "source_url": source.page_url,
            }
        )
    return rows


def clean_same_r() -> list[dict]:
    source = BY_NAME["SAME-R"]
    rows = []
    for r in read_rows(source.raw_path):
        test = r.get("SAME Test #", "")
        if not test:
            continue
        rows.append(
            {
                "sample_type": r.get("Sample Type", ""),
                "test": test,
                "description": _clean_cell(r.get("Description", "")),
                "inlet_velocity_cm_s": first_number(r.get("Inlet velocity (cm/s)")),
                "rt_r0": first_number(r.get("Rt/R0")),
                "duration_s": first_number(r.get("Duration (sec)")),
                "primary_aging_s": first_number(r.get("Primary aging time (sec)")),
                "primary_mixing_s": first_number(r.get("Primary mixing time (sec)")),
                "net_aging_s": first_number(_clean_cell(r.get("Net aging time (sec)", ""))),
                "source_url": source.page_url,
            }
        )
    return rows


def main() -> None:
    for rows, name in (
        (clean_flex2(), "flex2_conditions.csv"),
        (clean_same(), "same.csv"),
        (clean_same_r(), "same_r.csv"),
    ):
        print(
            f"clean_detection_and_flex2: wrote {_write(rows, OTHER_DIR / name)} ({len(rows)} rows)"
        )


if __name__ == "__main__":
    main()
