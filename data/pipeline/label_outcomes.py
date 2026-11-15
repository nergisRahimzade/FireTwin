"""DAT-02: write data/pipeline/label_outcomes.csv from the PSI experiment tables themselves.

Columns: test_id, outcome, spread_rate_mm_s, source_page. Nothing here is typed in by hand: every
label comes from a rule applied to cells of a PSI table, and `source_page` says which table, test
and cells justified it, so a reader can check the label against the source. A test whose table
gives no evidence stays "unknown" and is not written here.

Rules (strongest evidence first):
- FLEX (PSI-69), column "Test end": Completion -> burned, Extinction -> extinguished,
  Disruption (the droplet broke up) -> no label.
- Saffire-I/II (PSI-98, PSI-99), column "Burn Time (s)": a number -> burned; "Insignificant"
  -> extinguished (the flame did not sustain). Saffire-II's micro-gravity spread rate is copied
  when the table states one in mm/s; it is never estimated.
- BASS-II (PSI-25), "Fan display"/"Air display": a written extinction note ("ext", "out",
  "would not stay lit", flow reduced until blow-off) -> extinguished. With no such note, the
  gas sensors decide: burned only if CO2 rose by >= MIN_CO2_RISE_PCT or CO rose by >=
  MIN_CO_RISE_PPM between the initial and final readings (the flame consumed fuel and produced
  CO2/CO). This burned label is an INFERENCE from sensors, not a statement in the table, and
  `source_page` says so. The thresholds are the smallest rises seen in the tests whose table notes
  explicitly record an extinction after burning, i.e. tests where a flame certainly existed.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from clean_bass_ii import outcome_and_flow
from psi_sources import BY_NAME, ROOT, first_number, read_rows

log = logging.getLogger("label_outcomes")

OUT = ROOT / "data" / "pipeline" / "label_outcomes.csv"
COLUMNS = ["test_id", "outcome", "spread_rate_mm_s", "source_page"]
MIN_CO2_RISE_PCT = 0.05
MIN_CO_RISE_PPM = 10.0


def _label(test_id: str, outcome: str, page: str, spread: float | None = None) -> dict:
    return {"test_id": test_id, "outcome": outcome, "spread_rate_mm_s": spread, "source_page": page}


def label_flex() -> list[dict]:
    mapping = {"completion": "burned", "extinction": "extinguished"}
    out = []
    for r in read_rows(BY_NAME["FLEX"].raw_path):
        number, end = r.get("FLEX Test #", ""), r.get("Test end", "").strip()
        outcome = mapping.get(end.lower())
        if number and outcome:
            out.append(
                _label(
                    f"FLEX-{number}", outcome, f"PSI-69 table, FLEX test {number}: Test end = {end}"
                )
            )
    return out


def label_saffire_1() -> list[dict]:
    out = []
    for r in read_rows(BY_NAME["Saffire-I"].raw_path):
        sample, burn = r.get("Sample Number", ""), r.get("Burn Time (s)", "")
        if re.match(r"^S\d+$", sample) and first_number(burn):
            out.append(
                _label(
                    f"Saffire-I-{sample}", "burned", f"PSI-98 table, {sample}: Burn Time = {burn} s"
                )
            )
    return out


def label_saffire_2() -> list[dict]:
    out = []
    for r in read_rows(BY_NAME["Saffire-II"].raw_path):
        sample, burn = r.get("Sample Number", ""), r.get("Burn Time (s)", "")
        if not re.match(r"^2-\d+$", sample) or not burn:
            continue
        spread_key = next(
            (k for k in r if k.endswith("g Spread Length") and not k.startswith("1")), ""
        )
        stated = re.search(r"(\d*\.?\d+)\s*mm/s", r.get(spread_key, ""))
        spread = float(stated.group(1)) if stated else None
        page = f"PSI-99 table, sample {sample}: Burn Time = {burn}"
        if burn.lower().startswith("insignificant"):
            out.append(
                _label(f"Saffire-II-{sample}", "extinguished", page + " (flame did not sustain)")
            )
        elif first_number(burn):
            if spread is not None:
                page += f"; micro-g spread rate stated as {spread:g} mm/s"
            out.append(_label(f"Saffire-II-{sample}", "burned", page, spread))
    return out


def label_bass_ii() -> list[dict]:
    out = []
    for r in read_rows(BY_NAME["BASS-II"].raw_path):
        test = r.get("Test #", "")
        if not test:
            continue
        fan, air = r.get("Fan display", ""), r.get("Air display", "")
        outcome, _ = outcome_and_flow(fan, air)
        if outcome == "extinguished":
            note = " | ".join(x for x in (fan, air) if x)[:80]
            out.append(
                _label(
                    f"BASS-II-{test}",
                    "extinguished",
                    f"PSI-25 table, test {test}: extinction written in fan/air display ({note})",
                )
            )
            continue
        co2_0, co2_1 = (
            first_number(r.get("Initial CO2 % by vol")),
            first_number(r.get("Final CO2 % by vol")),
        )
        co_0, co_1 = first_number(r.get("Initial CO (ppm)")), first_number(r.get("Final CO (ppm)"))
        rise_co2 = None if None in (co2_0, co2_1) else round(co2_1 - co2_0, 3)
        rise_co = None if None in (co_0, co_1) else round(co_1 - co_0, 1)
        if (rise_co2 or 0) >= MIN_CO2_RISE_PCT or (rise_co or 0) >= MIN_CO_RISE_PPM:
            out.append(
                _label(
                    f"BASS-II-{test}",
                    "burned",
                    f"PSI-25 table, test {test}: INFERRED burned from sensors, no extinction note; "
                    f"CO2 {co2_0}->{co2_1} %, CO {co_0}->{co_1} ppm",
                )
            )
    return out


def build_labels() -> list[dict]:
    rows = label_flex() + label_saffire_1() + label_saffire_2() + label_bass_ii()
    ids = [r["test_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(
            "label_outcomes: duplicate test_id in labels: "
            f"{sorted({i for i in ids if ids.count(i) > 1})[:5]}"
        )
    return sorted(rows, key=lambda r: r["test_id"])


def write_labels(rows: list[dict], path: Path = OUT) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row[k] is None else row[k]) for k in COLUMNS})
    return path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    try:
        rows = build_labels()
        write_labels(rows)
    except Exception:
        log.exception("label_outcomes failed")
        raise
    counts: dict[str, int] = {}
    for r in rows:
        key = f"{r['test_id'].rsplit('-', 1)[0]}:{r['outcome']}"
        counts[key] = counts.get(key, 0) + 1
    log.info("wrote %d labels to %s: %s", len(rows), OUT, dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
