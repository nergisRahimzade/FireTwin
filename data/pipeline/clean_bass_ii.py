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
    COLUMNS,
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


def _lowered_below_written(air: str) -> bool:
    """The crew kept lowering the air past the last speed written ('5 down to ext', 'pots ...')."""
    return lowest_flow_unknown(air) and "incr" not in air.lower()


def stated_extinction_flows(raw_path: Path | None = None) -> list[float]:
    """Extinction speeds the table writes out for tests where the air was lowered step by step."""
    out = []
    for r in read_rows(raw_path or SOURCE.raw_path):
        fan, air = r.get("Fan display", ""), r.get("Air display", "")
        speeds = flows(air)
        stepped_down = len(speeds) > 1 and speeds[-1] < speeds[0]
        if ending(fan, air) == "extinction" and stepped_down and not lowest_flow_unknown(air):
            out.append(min(speeds))
    return out


def imputed_extinction_flow(raw_path: Path | None = None) -> float | None:
    """For 'lowered until it went out' tests with no final speed: the median stated one."""
    stated = sorted(stated_extinction_flows(raw_path))
    if not stated:
        return None
    mid = len(stated) // 2
    return stated[mid] if len(stated) % 2 else (stated[mid - 1] + stated[mid]) / 2


def flow_ramp(fan: str, air: str, imputed: float | None) -> tuple[float | None, float | None, bool]:
    """(burning speed before the change, speed at extinction, whether that speed is imputed).

    A test where the crew changed the air until the flame went out holds two observations: the
    flame burned at the first speed written, then went out at the last one. When the air was
    lowered past the last speed written, the extinction speed is unknown and `imputed` is used
    (never above the lowest speed written).
    """
    speeds, how = flows(air), ending(fan, air)
    if how == "extinction" and speeds:
        if _lowered_below_written(air) and imputed is not None:
            end, was_imputed = min(imputed, min(speeds)), True
        elif _lowered_below_written(air):
            return None, None, False
        else:
            end, was_imputed = min(speeds), False
    elif how == "blowoff" and speeds:
        end, was_imputed = max(speeds), False
    else:
        return None, None, False
    start = speeds[0] if speeds[0] != end else None
    return start, end, was_imputed


def outcome_and_flow(fan: str, air: str) -> tuple[str, float | None]:
    speeds, how = flows(air), ending(fan, air)
    if how == "extinction":
        return "extinguished", None if lowest_flow_unknown(air) or not speeds else min(speeds)
    if how == "blowoff":
        return "extinguished", max(speeds) if speeds else None
    return "unknown", speeds[0] if speeds else None


def clean(raw_path: Path = SOURCE.raw_path) -> list[dict]:
    rows = []
    imputed = imputed_extinction_flow(raw_path)
    for r in read_rows(raw_path):
        test = r.get("Test #", "")
        if not test:
            continue
        fan, air = r.get("Fan display", ""), r.get("Air display", "")
        outcome, flow = outcome_and_flow(fan, air)
        start, end, _ = flow_ramp(fan, air, imputed)
        if outcome == "extinguished" and end is not None:
            flow = end  # includes the imputed speed for 'lowered until it went out' tests
        base = {
            "investigation": SOURCE.name,
            "fuel_type": "solid",
            "material": material(" ".join(r.get("Fuel Sample Material", "").split())),
            "hardware": "MSG",
            "o2_pct": rounded(first_number(r.get("Calibrated initial O2 % by vol"))),
            "pressure_kpa": None,
            "spread_rate_mm_s": None,
            "source_url": SOURCE.page_url,
            "is_synthetic": False,
        }
        rows.append(
            {"test_id": f"BASS-II-{test}", **base, "flow_cm_s": rounded(flow), "outcome": outcome}
        )
        if outcome == "extinguished" and start is not None:
            # Same sample, same O2: the flame was burning at the first speed before the change.
            rows.append(
                {
                    "test_id": f"BASS-II-{test}-start",
                    **base,
                    "flow_cm_s": rounded(start),
                    "outcome": "burned",
                }
            )
    return [{k: row[k] for k in COLUMNS} for row in rows]


def main() -> None:
    path = write_clean(clean(), CLEAN_DIR / "bass_ii.csv")
    print(f"clean_bass_ii: wrote {path}")


if __name__ == "__main__":
    main()
