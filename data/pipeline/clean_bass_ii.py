"""DAT-05: clean the BASS-II table (PSI-25) into data/clean/bass_ii.csv.

~130 solid-sample burns in a small wind tunnel in the Microgravity Science Glovebox. Most cells
are notes typed during the test: in many tests the crew lowered the airflow step by step until
the flame went out, so "Air display" reads like "5  3  2  ext". Rules (ported from the team's
earlier flame-in-freefall pipeline):
  - o2_pct: "Calibrated initial O2 % by vol". No cabin pressure in the table -> empty.
  - airflow speeds: numbers in "Air display" up to 40 cm/s (the tunnel's limit); numbers in
    brackets or after "pot" are fan settings, not speeds.
  - outcome, from the words typed in the fan and air cells: "ext", "out", "off", "would not
    stay lit" -> extinguished (at the lowest speed written, if known); "blowoff" -> extinguished
    (at the highest speed); "no ign" and anything unsaid -> unknown (no assumption it kept burning).
  - flow_cm_s: the speed where that outcome happened; otherwise the first speed written.
"""

from __future__ import annotations

import re
from pathlib import Path

from psi_sources import (
    BY_NAME,
    CLEAN_DIR,
    first_number,
    numbers_in,
    read_rows,
    rounded,
    write_clean,
)

SOURCE = BY_NAME["BASS-II"]
MAX_FLOW_CM_S = 40  # report: "a small wind tunnel which could impose airflow speeds up to 40 cm/s"


def material(text: str) -> str:
    """One name per kind of sample. Raises on anything new, so a new sample gets a rule."""
    t = text.lower()
    if "sibal" in t:
        return "Cotton-Fiberglass (SIBAL)"
    if "nomex" in t:
        return "Nomex"
    if "candle" in t or "wax" in t:
        return "Japan wax candle"
    if "spher" in t:
        return "Spherical section"
    if "rod" in t or "blac" in t:
        return "Black rod" if "blac" in t else "PMMA rod"
    if "film" in t or "micron" in t:
        return "PMMA film"
    if "pmma" in t or "slab" in t:
        return "PMMA slab"
    raise ValueError(f"unknown BASS-II sample {text!r}: add a rule to clean_bass_ii.material")


def flows(text: str) -> list[float]:
    """Air speeds (cm/s) in an 'Air display' cell, in the order they were set."""
    t = text.lower()
    outside = re.sub(r"\([^)]*\)", " ", t)
    outside = re.sub(r"\d*\.\d+\s*pot\b", " ", outside)  # '0.5 pot'
    outside = re.split(r"\bpots?\b", outside)[0]  # 'pot 0.4', 'pots 0.4 0.36 ...'
    speeds = [n for n in numbers_in(outside) if n <= MAX_FLOW_CM_S]
    if not speeds:  # one test writes fan readings outside the brackets and speeds inside
        bracketed = " ".join(re.findall(r"\(([^)]*)\)", t))
        speeds = [n for n in numbers_in(bracketed) if n <= MAX_FLOW_CM_S]
    return speeds


def lowest_flow_unknown(text: str) -> bool:
    """True when the air went lower than the speeds written ('down to ext', '<1', 'decr')."""
    t = text.lower()
    if re.search(r"down to|decr|low|<|\bpots?\b", t):
        return True
    bracketed = numbers_in(" ".join(re.findall(r"\(([^)]*)\)", t)))
    if bracketed and max(bracketed) < 2 and flows(text):
        return True
    return "incr" in t and len(flows(text)) < 2


def ending(fan: str, air: str) -> str | None:
    t = f"{fan} {air}".lower()
    if "no ign" in t:
        return "no ignition"
    if "blowoff" in t or "blow off" in t:
        return "blowoff"
    if re.search(r"ext|\bout\b|\boff\b|would not stay lit", t):
        return "extinction"
    return None


def outcome_and_flow(fan: str, air: str) -> tuple[str, float | None]:
    speeds, how = flows(air), ending(fan, air)
    if how == "extinction":
        return "extinguished", None if lowest_flow_unknown(air) or not speeds else min(speeds)
    if how == "blowoff":
        return "extinguished", max(speeds) if speeds else None
    return "unknown", speeds[0] if speeds else None


def clean(raw_path: Path = SOURCE.raw_path) -> list[dict]:
    rows = []
    for r in read_rows(raw_path):
        test = r.get("Test #", "")
        if not test:
            continue
        outcome, flow = outcome_and_flow(r.get("Fan display", ""), r.get("Air display", ""))
        rows.append(
            {
                "test_id": f"BASS-II-{test}",
                "investigation": SOURCE.name,
                "fuel_type": "solid",
                "material": material(" ".join(r.get("Fuel Sample Material", "").split())),
                "hardware": "MSG",
                "o2_pct": rounded(first_number(r.get("Calibrated initial O2 % by vol"))),
                "pressure_kpa": None,
                "flow_cm_s": rounded(flow),
                "outcome": outcome,
                "spread_rate_mm_s": None,
                "source_url": SOURCE.page_url,
                "is_synthetic": False,
            }
        )
    return rows


def main() -> None:
    path = write_clean(clean(), CLEAN_DIR / "bass_ii.csv")
    print(f"clean_bass_ii: wrote {path}")


if __name__ == "__main__":
    main()
